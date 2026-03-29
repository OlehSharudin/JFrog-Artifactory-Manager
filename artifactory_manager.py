#!/usr/bin/env python3
"""
JFrog Artifactory Manager
A comprehensive tool for managing JFrog Artifactory operations including:
- Upload files/folders to Artifactory
- Scan/browse Artifactory structure with filters and export
- Download artifacts from Artifactory
- Delete artifacts from Artifactory
- Automatic JFrog CLI installation and configuration
"""

import os
import sys
import subprocess
import requests
import logging
import json
import platform
import zipfile
import tarfile
import shutil
from pathlib import Path
from typing import Optional, Dict, List
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from datetime import datetime
import threading
import re


class JFrogCLIManager:
    """Manages JFrog CLI installation and configuration"""
    
    def __init__(self):
        self.system = platform.system().lower()
        self.cli_version = "2.52.10"
        self.install_dir = self._get_install_dir()
        self.cli_executable = self._get_cli_executable()
        
    def _get_install_dir(self) -> Path:
        """Get installation directory based on OS"""
        if self.system == "windows":
            return Path(os.environ.get('LOCALAPPDATA', 'C:\\Tools')) / "jfrog"
        else:
            return Path.home() / ".jfrog-cli"
    
    def _get_cli_executable(self) -> Path:
        """Get CLI executable path based on OS"""
        if self.system == "windows":
            return self.install_dir / "jf.exe"
        else:
            return self.install_dir / "jf"
    
    def _get_download_url(self) -> str:
        """Get download URL based on OS and architecture"""
        base_url = f"https://releases.jfrog.io/artifactory/jfrog-cli/v2-jf/{self.cli_version}/jfrog-cli"
        
        if self.system == "windows":
            return f"{base_url}-windows-amd64/jf.exe"
        elif self.system == "darwin":
            return f"{base_url}-mac-386/jf"
        else:  # linux
            return f"{base_url}-linux-amd64/jf"
    
    def is_installed(self) -> bool:
        """Check if JFrog CLI is installed"""
        return self.cli_executable.exists()
    
    def install(self) -> bool:
        """Install JFrog CLI"""
        try:
            logging.info("Installing JFrog CLI...")
            
            # Create installation directory
            self.install_dir.mkdir(parents=True, exist_ok=True)
            
            # Download CLI
            download_url = self._get_download_url()
            logging.info(f"Downloading from: {download_url}")
            
            response = requests.get(download_url, stream=True)
            response.raise_for_status()
            
            # Save executable
            with open(self.cli_executable, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Make executable on Unix-like systems
            if self.system != "windows":
                os.chmod(self.cli_executable, 0o755)
            
            # Verify installation
            result = subprocess.run([str(self.cli_executable), "--version"], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                logging.info(f"JFrog CLI installed successfully: {result.stdout.strip()}")
                return True
            else:
                logging.error("JFrog CLI installation verification failed")
                return False
                
        except Exception as e:
            logging.error(f"Failed to install JFrog CLI: {e}")
            return False
    
    def configure_server(self, server_id: str, url: str, token: str, user: str = None) -> bool:
        """Configure JFrog CLI server"""
        try:
            # Check if server is already configured
            result = subprocess.run([str(self.cli_executable), "config", "show"], 
                                  capture_output=True, text=True)
            
            if server_id in result.stdout:
                logging.info(f"Server '{server_id}' already configured")
                # Remove old configuration
                subprocess.run([str(self.cli_executable), "config", "remove", 
                              server_id, "--quiet"], 
                             capture_output=True)
            
            # Normalize URL - remove trailing /artifactory/ if present
            normalized_url = url.rstrip('/')
            if normalized_url.endswith('/artifactory'):
                normalized_url = normalized_url[:-len('/artifactory')]
            
            # Ensure URL ends with single /
            if not normalized_url.endswith('/'):
                normalized_url += '/'
            
            logging.info(f"Configuring with normalized URL: {normalized_url}")
            
            # Add new configuration
            cmd = [
                str(self.cli_executable), "config", "add", server_id,
                f"--url={normalized_url}",
                f"--access-token={token}",
                "--interactive=false",
                "--overwrite"
            ]
            
            # Add user only if provided
            if user:
                cmd.insert(4, f"--user={user}")
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                logging.info(f"Server '{server_id}' configured successfully")
                return True
            else:
                logging.error(f"Failed to configure server: {result.stderr}")
                return False
                
        except Exception as e:
            logging.error(f"Error configuring server: {e}")
            return False
    
    def remove_server(self, server_id: str) -> bool:
        """Remove JFrog CLI server configuration"""
        try:
            subprocess.run([str(self.cli_executable), "config", "remove", 
                          server_id, "--quiet"], 
                         capture_output=True)
            return True
        except Exception as e:
            logging.error(f"Error removing server configuration: {e}")
            return False


class ArtifactoryManager:
    """Manages Artifactory operations"""
    
    def __init__(self, cli_manager: JFrogCLIManager):
        self.cli_manager = cli_manager
        self.base_url = None
        self.access_token = None
        
    def set_credentials(self, base_url: str, access_token: str):
        """Set Artifactory credentials"""
        self.base_url = base_url.rstrip('/')
        self.access_token = access_token
    
    def scan_repository(self, repo_path: str, max_depth: int = 3, 
                       name_filter: str = "", file_filter: str = "") -> Dict:
        """Scan repository structure with filters"""
        try:
            tree = self._build_tree(repo_path, depth=1, max_depth=max_depth, 
                                   name_filter=name_filter, file_filter=file_filter)
            return {"success": True, "tree": tree}
        except Exception as e:
            logging.error(f"Error scanning repository: {e}")
            return {"success": False, "error": str(e)}
    
    def _matches_filter(self, name: str, filter_pattern: str) -> bool:
        """Check if name matches filter pattern (supports wildcards)"""
        if not filter_pattern:
            return True
        
        # Convert wildcard pattern to regex
        pattern = filter_pattern.replace("*", ".*").replace("?", ".")
        try:
            return bool(re.search(pattern, name, re.IGNORECASE))
        except Exception:
            # If regex fails, try simple substring match
            return filter_pattern.lower() in name.lower()
    
    def _build_tree(self, folder_path: str, depth: int = 1, max_depth: int = 3,
                   name_filter: str = "", file_filter: str = "") -> Dict:
        """Recursively build tree structure with filters"""
        if depth > max_depth:
            return {"name": folder_path.split("/")[-1], "type": "folder", "children": []}
        
        url = f"{self.base_url}/api/storage/{folder_path}"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        folder_name = folder_path.split("/")[-1] or folder_path
        
        tree = {
            "name": folder_name,
            "type": "folder",
            "path": folder_path,
            "children": []
        }
        
        for child in data.get("children", []):
            child_name = child["uri"].strip("/")
            child_path = f"{folder_path}/{child_name}"
            
            # Apply filters
            if name_filter and not self._matches_filter(child_name, name_filter):
                continue
            
            if child["folder"]:
                child_tree = self._build_tree(child_path, depth + 1, max_depth, 
                                             name_filter, file_filter)
                if child_tree["children"] or not name_filter:  # Include if has children or no filter
                    tree["children"].append(child_tree)
            else:
                # Apply file-specific filter
                if file_filter and not self._matches_filter(child_name, file_filter):
                    continue
                tree["children"].append({
                    "name": child_name,
                    "type": "file",
                    "path": child_path
                })
        
        return tree
    
    def export_tree_to_text(self, tree: Dict, indent: int = 0) -> str:
        """Export tree structure to text format"""
        lines = []
        prefix = "  " * indent
        icon = "📁" if tree["type"] == "folder" else "📄"
        
        lines.append(f"{prefix}{icon} {tree['name']}")
        
        for child in tree.get("children", []):
            lines.append(self.export_tree_to_text(child, indent + 1))
        
        return "\n".join(lines)
    
    def upload_files(self, local_path: str, repo_path: str, server_id: str, 
                     flat: bool = False, recursive: bool = True,
                     progress_callback=None, command_callback=None) -> Dict:
        """Upload files to Artifactory"""
        try:
            original_dir = os.getcwd()
            
            # If local_path is a file, upload it directly
            if os.path.isfile(local_path):
                parent_dir = os.path.dirname(local_path)
                file_name = os.path.basename(local_path)
                os.chdir(parent_dir)
                source_pattern = file_name
            else:
                os.chdir(local_path)
                source_pattern = "./*"
            
            cmd = [
                str(self.cli_manager.cli_executable), "rt", "upload",
                source_pattern,
                repo_path,
                f"--server-id={server_id}",
                f"--flat={'true' if flat else 'false'}",
                f"--recursive={'true' if recursive else 'false'}"
            ]
            
            if command_callback:
                command_callback(" ".join(cmd))
            
            if progress_callback:
                progress_callback("Starting upload...\n")
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            stdout, stderr = process.communicate()
            
            os.chdir(original_dir)
            
            if process.returncode == 0:
                if progress_callback:
                    progress_callback(f"Upload completed successfully\n{stdout}\n")
                return {"success": True, "output": stdout}
            else:
                if progress_callback:
                    progress_callback(f"Upload failed\n{stderr}\n")
                return {"success": False, "error": stderr}
                
        except Exception as e:
            if 'original_dir' in locals():
                os.chdir(original_dir)
            logging.error(f"Error uploading files: {e}")
            return {"success": False, "error": str(e)}
    
    def download_files(self, repo_path: str, local_path: str, server_id: str,
                       flat: bool = False, recursive: bool = True,
                       progress_callback=None, command_callback=None) -> Dict:
        """Download files from Artifactory"""
        try:
            # Ensure destination exists
            os.makedirs(local_path, exist_ok=True)
            
            cmd = [
                str(self.cli_manager.cli_executable), "rt", "download",
                repo_path,
                local_path,
                f"--server-id={server_id}",
                f"--flat={'true' if flat else 'false'}",
                f"--recursive={'true' if recursive else 'false'}"
            ]
            
            if command_callback:
                command_callback(" ".join(cmd))
            
            if progress_callback:
                progress_callback("Starting download...\n")
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            stdout, stderr = process.communicate()
            
            if process.returncode == 0:
                if progress_callback:
                    progress_callback(f"Download completed successfully\n{stdout}\n")
                return {"success": True, "output": stdout, "path": local_path}
            else:
                if progress_callback:
                    progress_callback(f"Download failed\n{stderr}\n")
                return {"success": False, "error": stderr}
                
        except Exception as e:
            logging.error(f"Error downloading files: {e}")
            return {"success": False, "error": str(e)}
    
    def delete_files(self, repo_path: str, server_id: str, recursive: bool = True,
                     dry_run: bool = False, progress_callback=None, 
                     command_callback=None) -> Dict:
        """Delete files from Artifactory"""
        try:
            cmd = [
                str(self.cli_manager.cli_executable), "rt", "delete",
                repo_path,
                f"--server-id={server_id}",
                f"--recursive={'true' if recursive else 'false'}",
                "--quiet"
            ]
            
            if dry_run:
                cmd.append("--dry-run")
            
            if command_callback:
                command_callback(" ".join(cmd))
            
            if progress_callback:
                if dry_run:
                    progress_callback("Running dry-run (no files will be deleted)...\n")
                else:
                    progress_callback("Starting deletion...\n")
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            stdout, stderr = process.communicate()
            
            if process.returncode == 0:
                if progress_callback:
                    if dry_run:
                        progress_callback(f"Dry-run completed\n{stdout}\n")
                    else:
                        progress_callback(f"Deletion completed successfully\n{stdout}\n")
                return {"success": True, "output": stdout, "dry_run": dry_run}
            else:
                if progress_callback:
                    progress_callback(f"Deletion failed\n{stderr}\n")
                return {"success": False, "error": stderr}
                
        except Exception as e:
            logging.error(f"Error deleting files: {e}")
            return {"success": False, "error": str(e)}


class ArtifactoryGUI:
    """GUI for JFrog Artifactory Manager"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("JFrog Artifactory Manager v2.0")
        self.root.geometry("1100x750")
        
        # Initialize managers
        self.cli_manager = JFrogCLIManager()
        self.artifactory_manager = ArtifactoryManager(self.cli_manager)
        
        # Session credentials (not saved)
        self.session_configured = False
        
        # Setup logging
        self.setup_logging()
        
        # Create GUI
        self.create_widgets()
        
        # Check JFrog CLI installation
        self.root.after(100, self.check_cli_installation)
    
    def setup_logging(self):
        """Setup logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('artifactory_manager.log'),
                logging.StreamHandler()
            ]
        )
    
    def create_widgets(self):
        """Create GUI widgets"""
        # Create notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Create tabs
        self.create_settings_tab()
        self.create_upload_tab()
        self.create_scan_tab()
        self.create_download_tab()
        self.create_delete_tab()
        self.create_about_tab()
        
        # Status bar
        status_frame = ttk.Frame(self.root)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.status_var = tk.StringVar()
        self.status_var.set("Ready - Please configure credentials")
        status_bar = ttk.Label(status_frame, textvariable=self.status_var, 
                              relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Session indicator
        self.session_var = tk.StringVar()
        self.session_var.set("❌ Not Configured")
        session_label = ttk.Label(status_frame, textvariable=self.session_var,
                                 relief=tk.SUNKEN, anchor=tk.E)
        session_label.pack(side=tk.RIGHT, padx=5)
    
    def create_settings_tab(self):
        """Create settings tab"""
        settings_frame = ttk.Frame(self.notebook)
        self.notebook.add(settings_frame, text="⚙️ Settings")
        
        # Main container
        container = ttk.Frame(settings_frame, padding="10")
        container.pack(fill='both', expand=True)
        
        # JFrog CLI Status
        cli_frame = ttk.LabelFrame(container, text="JFrog CLI Status", padding="10")
        cli_frame.pack(fill='x', pady=(0, 10))
        
        self.cli_status_var = tk.StringVar()
        ttk.Label(cli_frame, textvariable=self.cli_status_var).pack(anchor='w')
        
        btn_frame = ttk.Frame(cli_frame)
        btn_frame.pack(fill='x', pady=(5, 0))
        
        ttk.Button(btn_frame, text="Install JFrog CLI", 
                  command=self.install_cli).pack(side='left', padx=(0, 5))
        ttk.Button(btn_frame, text="Check Status", 
                  command=self.check_cli_installation).pack(side='left')
        
        # Security Notice
        notice_frame = ttk.LabelFrame(container, text="Security Notice", padding="10")
        notice_frame.pack(fill='x', pady=(0, 10))
        
        notice_text = """🔒 Security: Credentials are used for the current session only and are NOT saved to disk.
You will need to enter your credentials each time you start the application.
Configuration is cleared when you close the application or click 'Clear Session'."""
        
        ttk.Label(notice_frame, text=notice_text, wraplength=900, 
                 justify='left', foreground='blue').pack(anchor='w')
        
        # Artifactory Configuration
        config_frame = ttk.LabelFrame(container, text="Artifactory Configuration (Session Only)", 
                                     padding="10")
        config_frame.pack(fill='both', expand=True)
        
        # Server ID
        ttk.Label(config_frame, text="Server ID:").grid(row=0, column=0, 
                                                        sticky='w', pady=5)
        self.server_id_var = tk.StringVar(value="my-server")
        ttk.Entry(config_frame, textvariable=self.server_id_var, 
                 width=40).grid(row=0, column=1, sticky='ew', pady=5)
        
        # Artifactory URL
        ttk.Label(config_frame, text="Artifactory URL:").grid(row=1, column=0, 
                                                              sticky='w', pady=5)
        self.url_var = tk.StringVar(value="https://your-instance.jfrog.io/artifactory/")
        ttk.Entry(config_frame, textvariable=self.url_var, 
                 width=40).grid(row=1, column=1, sticky='ew', pady=5)
        
        # Username (optional)
        ttk.Label(config_frame, text="Username (optional):").grid(row=2, column=0, 
                                                       sticky='w', pady=5)
        self.user_var = tk.StringVar(value="")
        username_entry = ttk.Entry(config_frame, textvariable=self.user_var, width=40)
        username_entry.grid(row=2, column=1, sticky='ew', pady=5)
        
        ttk.Label(config_frame, text="Usually not required with access token", 
                 font=('Arial', 8, 'italic'), foreground='gray').grid(
            row=2, column=2, sticky='w', pady=5, padx=(5, 0))
        
        # Access Token (required)
        ttk.Label(config_frame, text="Access Token *:").grid(row=3, column=0, 
                                                           sticky='w', pady=5)
        self.token_var = tk.StringVar()
        ttk.Entry(config_frame, textvariable=self.token_var, 
                 width=40, show="*").grid(row=3, column=1, sticky='ew', pady=5)
        
        ttk.Label(config_frame, text="Required", 
                 font=('Arial', 8, 'italic'), foreground='red').grid(
            row=3, column=2, sticky='w', pady=5, padx=(5, 0))
        
        # Buttons
        btn_frame = ttk.Frame(config_frame)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=10)
        
        ttk.Button(btn_frame, text="Configure Session", 
                  command=self.save_configuration).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Test Connection", 
                  command=self.test_connection).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Clear Session", 
                  command=self.clear_session).pack(side='left', padx=5)
        
        config_frame.columnconfigure(1, weight=1)
    
    def create_upload_tab(self):
        """Create upload tab"""
        upload_frame = ttk.Frame(self.notebook)
        self.notebook.add(upload_frame, text="⬆️ Upload")
        
        container = ttk.Frame(upload_frame, padding="10")
        container.pack(fill='both', expand=True)
        
        # Local Path
        path_frame = ttk.LabelFrame(container, text="Local Path", padding="10")
        path_frame.pack(fill='x', pady=(0, 10))
        
        local_path_frame = ttk.Frame(path_frame)
        local_path_frame.pack(fill='x')
        
        self.upload_local_var = tk.StringVar()
        ttk.Entry(local_path_frame, textvariable=self.upload_local_var).pack(
            side='left', fill='x', expand=True, padx=(0, 5))
        ttk.Button(local_path_frame, text="Browse Folder", 
                  command=self.browse_upload_folder).pack(side='left', padx=(0, 5))
        ttk.Button(local_path_frame, text="Browse File", 
                  command=self.browse_upload_file).pack(side='left')
        
        # Repository Path
        repo_frame = ttk.LabelFrame(container, text="Target Repository Path", 
                                   padding="10")
        repo_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Label(repo_frame, text="Example: my-repo/path/to/artifacts/").pack(
            anchor='w', pady=(0, 5))
        self.upload_repo_var = tk.StringVar(
            value="my-repo/path/to/artifacts/")
        ttk.Entry(repo_frame, textvariable=self.upload_repo_var).pack(fill='x')
        
        # Options
        options_frame = ttk.LabelFrame(container, text="Options", padding="10")
        options_frame.pack(fill='x', pady=(0, 10))
        
        self.upload_flat_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="Flat structure (don't preserve folders)", 
                       variable=self.upload_flat_var).pack(anchor='w')
        
        self.upload_recursive_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Recursive (include subfolders)", 
                       variable=self.upload_recursive_var).pack(anchor='w')
        
        # Progress bar with Windows XP-style animation
        progress_bar_frame = ttk.Frame(container)
        progress_bar_frame.pack(fill='x', pady=(0, 5))
        
        ttk.Label(progress_bar_frame, text="Progress:").pack(side='left', padx=(0, 5))
        self.upload_progress_bar = ttk.Progressbar(
            progress_bar_frame, mode='determinate', maximum=100)
        self.upload_progress_bar.pack(side='left', fill='x', expand=True)
        
        # XP animation state
        self.upload_xp_value = 0
        self.upload_xp_active = False
        
        # Command display
        cmd_frame = ttk.LabelFrame(container, text="Command", padding="5")
        cmd_frame.pack(fill='x', pady=(0, 5))
        
        self.upload_command = scrolledtext.ScrolledText(
            cmd_frame, height=2, state='disabled', wrap=tk.WORD)
        self.upload_command.pack(fill='x')
        
        # Output
        output_frame = ttk.LabelFrame(container, text="Output", padding="5")
        output_frame.pack(fill='both', expand=True)
        
        self.upload_progress = scrolledtext.ScrolledText(
            output_frame, height=8, state='disabled')
        self.upload_progress.pack(fill='both', expand=True)
        
        # Upload button
        ttk.Button(container, text="Start Upload", 
                  command=self.start_upload).pack(pady=10)
    
    def create_scan_tab(self):
        """Create scan tab with filters and export"""
        scan_frame = ttk.Frame(self.notebook)
        self.notebook.add(scan_frame, text="🔍 Scan")
        
        container = ttk.Frame(scan_frame, padding="10")
        container.pack(fill='both', expand=True)
        
        # Repository Path and Controls
        controls_frame = ttk.LabelFrame(container, text="Scan Configuration", 
                                       padding="10")
        controls_frame.pack(fill='x', pady=(0, 10))
        
        # Repository Path
        ttk.Label(controls_frame, text="Repository Path:").grid(
            row=0, column=0, sticky='w', pady=5)
        self.scan_repo_var = tk.StringVar(value="my-repo/")
        ttk.Entry(controls_frame, textvariable=self.scan_repo_var).grid(
            row=0, column=1, sticky='ew', pady=5, padx=5)
        
        # Max Depth
        ttk.Label(controls_frame, text="Max Depth:").grid(
            row=1, column=0, sticky='w', pady=5)
        self.scan_depth_var = tk.IntVar(value=3)
        ttk.Spinbox(controls_frame, from_=1, to=10, 
                   textvariable=self.scan_depth_var, width=10).grid(
            row=1, column=1, sticky='w', pady=5, padx=5)
        
        controls_frame.columnconfigure(1, weight=1)
        
        # Filters
        filter_frame = ttk.LabelFrame(container, text="Filters (use * as wildcard)", 
                                     padding="10")
        filter_frame.pack(fill='x', pady=(0, 10))
        
        # Name filter
        ttk.Label(filter_frame, text="Name Filter:").grid(
            row=0, column=0, sticky='w', pady=5)
        self.scan_name_filter_var = tk.StringVar()
        ttk.Entry(filter_frame, textvariable=self.scan_name_filter_var).grid(
            row=0, column=1, sticky='ew', pady=5, padx=5)
        ttk.Label(filter_frame, text="(e.g., *test* or build*)").grid(
            row=0, column=2, sticky='w', pady=5)
        
        # File filter
        ttk.Label(filter_frame, text="File Filter:").grid(
            row=1, column=0, sticky='w', pady=5)
        self.scan_file_filter_var = tk.StringVar()
        ttk.Entry(filter_frame, textvariable=self.scan_file_filter_var).grid(
            row=1, column=1, sticky='ew', pady=5, padx=5)
        ttk.Label(filter_frame, text="(e.g., *.zip or *.log)").grid(
            row=1, column=2, sticky='w', pady=5)
        
        filter_frame.columnconfigure(1, weight=1)
        
        # Buttons
        btn_frame = ttk.Frame(container)
        btn_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Button(btn_frame, text="🔍 Scan Repository", 
                  command=self.start_scan).pack(side='left', padx=(0, 5))
        ttk.Button(btn_frame, text="💾 Export to Text File", 
                  command=self.export_scan_results).pack(side='left', padx=(0, 5))
        ttk.Button(btn_frame, text="🗑️ Clear Results", 
                  command=self.clear_scan_results).pack(side='left')
        
        # Progress bar with Windows XP-style animation
        self.scan_progress_bar = ttk.Progressbar(
            container, mode='determinate', maximum=100)
        self.scan_progress_bar.pack(fill='x', pady=(0, 5))
        
        # XP animation state
        self.scan_xp_value = 0
        self.scan_xp_active = False
        
        # Tree view
        tree_frame = ttk.LabelFrame(container, text="Repository Structure", 
                                   padding="10")
        tree_frame.pack(fill='both', expand=True)
        
        # Scrollbars
        tree_scroll_y = ttk.Scrollbar(tree_frame, orient='vertical')
        tree_scroll_y.pack(side='right', fill='y')
        
        tree_scroll_x = ttk.Scrollbar(tree_frame, orient='horizontal')
        tree_scroll_x.pack(side='bottom', fill='x')
        
        self.scan_tree = ttk.Treeview(
            tree_frame,
            yscrollcommand=tree_scroll_y.set,
            xscrollcommand=tree_scroll_x.set
        )
        self.scan_tree.pack(fill='both', expand=True)
        
        tree_scroll_y.config(command=self.scan_tree.yview)
        tree_scroll_x.config(command=self.scan_tree.xview)
        
        # Configure columns
        self.scan_tree['columns'] = ('Type', 'Path')
        self.scan_tree.column('#0', width=400)
        self.scan_tree.column('Type', width=100)
        self.scan_tree.column('Path', width=400)
        
        self.scan_tree.heading('#0', text='Name')
        self.scan_tree.heading('Type', text='Type')
        self.scan_tree.heading('Path', text='Path')
        
        # Store scan results for export
        self.last_scan_tree = None
    
    def create_download_tab(self):
        """Create download tab"""
        download_frame = ttk.Frame(self.notebook)
        self.notebook.add(download_frame, text="⬇️ Download")
        
        container = ttk.Frame(download_frame, padding="10")
        container.pack(fill='both', expand=True)
        
        # Repository Path
        repo_frame = ttk.LabelFrame(container, text="Repository Path to Download", 
                                   padding="10")
        repo_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Label(repo_frame, 
                 text="Example: my-repo/path/to/artifacts/build_0641/Release/").pack(
            anchor='w', pady=(0, 5))
        self.download_repo_var = tk.StringVar(
            value="my-repo/path/to/artifacts/")
        ttk.Entry(repo_frame, textvariable=self.download_repo_var).pack(fill='x')
        
        # Local Path
        local_frame = ttk.LabelFrame(container, text="Local Destination", 
                                    padding="10")
        local_frame.pack(fill='x', pady=(0, 10))
        
        local_path_frame = ttk.Frame(local_frame)
        local_path_frame.pack(fill='x')
        
        self.download_local_var = tk.StringVar(value=str(Path.home() / "Downloads"))
        ttk.Entry(local_path_frame, textvariable=self.download_local_var).pack(
            side='left', fill='x', expand=True, padx=(0, 5))
        ttk.Button(local_path_frame, text="Browse", 
                  command=self.browse_download_folder).pack(side='left')
        
        # Options
        options_frame = ttk.LabelFrame(container, text="Options", padding="10")
        options_frame.pack(fill='x', pady=(0, 10))
        
        self.download_flat_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="Flat structure (don't preserve folders)", 
                       variable=self.download_flat_var).pack(anchor='w')
        
        self.download_recursive_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Recursive (include subfolders)", 
                       variable=self.download_recursive_var).pack(anchor='w')
        
        # Progress bar with Windows XP-style animation
        progress_bar_frame = ttk.Frame(container)
        progress_bar_frame.pack(fill='x', pady=(0, 5))
        
        ttk.Label(progress_bar_frame, text="Progress:").pack(side='left', padx=(0, 5))
        self.download_progress_bar = ttk.Progressbar(
            progress_bar_frame, mode='determinate', maximum=100)
        self.download_progress_bar.pack(side='left', fill='x', expand=True)
        
        # XP animation state
        self.download_xp_value = 0
        self.download_xp_active = False
        
        # Command display
        cmd_frame = ttk.LabelFrame(container, text="Command", padding="5")
        cmd_frame.pack(fill='x', pady=(0, 5))
        
        self.download_command = scrolledtext.ScrolledText(
            cmd_frame, height=2, state='disabled', wrap=tk.WORD)
        self.download_command.pack(fill='x')
        
        # Output
        output_frame = ttk.LabelFrame(container, text="Output", padding="5")
        output_frame.pack(fill='both', expand=True)
        
        self.download_progress = scrolledtext.ScrolledText(
            output_frame, height=8, state='disabled')
        self.download_progress.pack(fill='both', expand=True)
        
        # Download button
        ttk.Button(container, text="Start Download", 
                  command=self.start_download).pack(pady=10)
    
    def create_delete_tab(self):
        """Create delete tab"""
        delete_frame = ttk.Frame(self.notebook)
        self.notebook.add(delete_frame, text="🗑️ Delete")
        
        container = ttk.Frame(delete_frame, padding="10")
        container.pack(fill='both', expand=True)
        
        # Warning message
        warning_frame = ttk.Frame(container)
        warning_frame.pack(fill='x', pady=(0, 10))
        
        warning_label = ttk.Label(
            warning_frame,
            text="⚠️ WARNING: Deletion is permanent and cannot be undone!",
            foreground="red",
            font=('Arial', 11, 'bold')
        )
        warning_label.pack(pady=5)
        
        info_label = ttk.Label(
            warning_frame,
            text="Always use 'Dry Run' first to preview what will be deleted.",
            font=('Arial', 9, 'italic')
        )
        info_label.pack()
        
        # Repository Path
        repo_frame = ttk.LabelFrame(container, text="Repository Path to Delete", 
                                   padding="10")
        repo_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Label(repo_frame, 
                 text="Example: my-repo/path/to/artifacts/build_0641/").pack(
            anchor='w', pady=(0, 5))
        
        ttk.Label(repo_frame,
                 text="⚠️ Use wildcards carefully: */test.txt or *.log",
                 foreground="orange",
                 font=('Arial', 9, 'italic')).pack(anchor='w', pady=(0, 5))
        
        self.delete_repo_var = tk.StringVar(value="")
        ttk.Entry(repo_frame, textvariable=self.delete_repo_var).pack(fill='x')
        
        # Options
        options_frame = ttk.LabelFrame(container, text="Options", padding="10")
        options_frame.pack(fill='x', pady=(0, 10))
        
        self.delete_recursive_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Recursive (delete folders and all contents)", 
                       variable=self.delete_recursive_var).pack(anchor='w')
        
        self.delete_dryrun_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, 
                       text="Dry Run (preview only, don't actually delete)", 
                       variable=self.delete_dryrun_var).pack(anchor='w')
        
        # Confirmation frame
        confirm_frame = ttk.LabelFrame(container, text="Confirmation", padding="10")
        confirm_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Label(confirm_frame, 
                 text="Type the path again to confirm deletion:",
                 font=('Arial', 9, 'bold')).pack(anchor='w', pady=(0, 5))
        
        self.delete_confirm_var = tk.StringVar()
        self.delete_confirm_entry = ttk.Entry(confirm_frame, 
                                             textvariable=self.delete_confirm_var)
        self.delete_confirm_entry.pack(fill='x')
        
        # Progress bar with Windows XP-style animation
        progress_bar_frame = ttk.Frame(container)
        progress_bar_frame.pack(fill='x', pady=(0, 5))
        
        ttk.Label(progress_bar_frame, text="Progress:").pack(side='left', padx=(0, 5))
        self.delete_progress_bar = ttk.Progressbar(
            progress_bar_frame, mode='determinate', maximum=100)
        self.delete_progress_bar.pack(side='left', fill='x', expand=True)
        
        # XP animation state
        self.delete_xp_value = 0
        self.delete_xp_active = False
        
        # Command display
        cmd_frame = ttk.LabelFrame(container, text="Command", padding="5")
        cmd_frame.pack(fill='x', pady=(0, 5))
        
        self.delete_command = scrolledtext.ScrolledText(
            cmd_frame, height=2, state='disabled', wrap=tk.WORD)
        self.delete_command.pack(fill='x')
        
        # Output
        output_frame = ttk.LabelFrame(container, text="Output", padding="5")
        output_frame.pack(fill='both', expand=True)
        
        self.delete_progress = scrolledtext.ScrolledText(
            output_frame, height=6, state='disabled')
        self.delete_progress.pack(fill='both', expand=True)
        
        # Buttons
        button_frame = ttk.Frame(container)
        button_frame.pack(pady=10)
        
        ttk.Button(button_frame, text="Dry Run (Preview)", 
                  command=self.start_delete_dryrun).pack(side='left', padx=5)
        
        ttk.Button(button_frame, text="Delete Files", 
                  command=self.start_delete).pack(side='left', padx=5)
    
    def create_about_tab(self):
        """Create about tab with instructions and author information"""
        about_frame = ttk.Frame(self.notebook)
        self.notebook.add(about_frame, text="ℹ️ About")
        
        # Create scrollable container
        canvas = tk.Canvas(about_frame)
        scrollbar = ttk.Scrollbar(about_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Main container with padding
        container = ttk.Frame(scrollable_frame, padding="20")
        container.pack(fill='both', expand=True)
        
        # Title
        title_label = ttk.Label(
            container, 
            text="JFrog Artifactory Manager",
            font=('Arial', 16, 'bold')
        )
        title_label.pack(pady=(0, 5))
        
        version_label = ttk.Label(
            container,
            text="Version 2.0",
            font=('Arial', 10)
        )
        version_label.pack(pady=(0, 20))
        
        # Author Information
        author_frame = ttk.LabelFrame(container, text="Author Information", padding="15")
        author_frame.pack(fill='x', pady=(0, 15))
        
        author_text = """👤 Created by: Oleh Sharudin
📅 Date: December 3, 2025
💼 Role: DevOps Engineer
🔗 GitHub: https://github.com/OlehSharudin"""
        
        author_label = ttk.Label(author_frame, text=author_text, justify='left')
        author_label.pack(anchor='w')
        
        # What's New in v2.0
        whatsnew_frame = ttk.LabelFrame(container, text="🆕 What's New in v2.0", padding="15")
        whatsnew_frame.pack(fill='x', pady=(0, 15))
        
        whatsnew_text = """✨ Enhanced Security:
   • No hardcoded credentials - all credentials are session-only
   • Credentials are never saved to disk
   • Clear session functionality to remove sensitive data

🔍 Improved Scanning:
   • Default scan path: my-repo/ (max depth: 3)
   • Advanced filtering: name patterns and file extensions
   • Export scan results to text file (tree format)
   • Wildcard support in filters (*, ?)

📊 Better Status Handling:
   • Progress bars for all operations (upload/download/delete/scan)
   • Command execution viewer for all operations
   • Real-time operation status display
   • Session configuration indicator

🎨 Enhanced User Interface:
   • Dedicated command display for each operation
   • Improved output formatting and readability
   • Better error messages and user feedback
   • Updated color scheme and layout"""
        
        whatsnew_label = ttk.Label(whatsnew_frame, text=whatsnew_text, justify='left')
        whatsnew_label.pack(anchor='w')
        
        # Quick Start Guide
        quickstart_frame = ttk.LabelFrame(container, text="🚀 Quick Start Guide", padding="15")
        quickstart_frame.pack(fill='x', pady=(0, 15))
        
        quickstart_text = """1. Install JFrog CLI (Settings tab)
   • Click "Install JFrog CLI" button
   • Wait for installation to complete
   • Status will show green checkmark when ready

2. Configure Session (Settings tab) - REQUIRED EVERY TIME
   • Enter your Artifactory URL
   • Enter your access token (required)
   • Username is optional (usually not needed)
   • Click "Configure Session"
   • Test connection to verify
   • Note: Credentials are NOT saved and must be entered each session

3. Start Using the Tool
   • Upload: Transfer files to Artifactory
   • Scan: Browse repository structure with filters
   • Download: Get files from Artifactory
   • Delete: Remove files/folders (use with caution!)

4. End Session
   • Click "Clear Session" to remove credentials
   • Or simply close the application"""
        
        quickstart_label = ttk.Label(quickstart_frame, text=quickstart_text, justify='left')
        quickstart_label.pack(anchor='w')
        
        # Scan Tab Instructions
        scan_frame = ttk.LabelFrame(container, text="🔍 Scan Tab Features", padding="15")
        scan_frame.pack(fill='x', pady=(0, 15))
        
        scan_text = """📂 Default Configuration:
   • Initial Path: my-repo/
   • Max Depth: 3 levels (adjustable 1-10)

🔎 Advanced Filtering:
   • Name Filter: Filter folders/files by name
     Examples: *test*, build*, *debug*
   • File Filter: Filter only files by extension/name
     Examples: *.zip, *.log, release*
   • Wildcards: Use * (any chars) or ? (single char)

💾 Export Results:
   • Click "Export to Text File" after scanning
   • Saves tree structure with folders (📁) and files (📄)
   • Choose destination and filename
   • Perfect for documentation or sharing

🎯 Usage Tips:
   • Start with broad filters, then narrow down
   • Combine name and file filters for precise results
   • Use lower max depth for faster scans
   • Export results before changing filters"""
        
        scan_label = ttk.Label(scan_frame, text=scan_text, justify='left')
        scan_label.pack(anchor='w')
        
        # Progress & Status
        progress_frame = ttk.LabelFrame(container, text="📊 Progress & Status Features", padding="15")
        progress_frame.pack(fill='x', pady=(0, 15))
        
        progress_text = """🔄 Progress Bars:
   • Visual indication for all long-running operations
   • Animated progress during upload/download/scan/delete
   • Automatically stops when operation completes

⌨️ Command Viewer:
   • Shows exact JFrog CLI command being executed
   • Useful for debugging and learning CLI syntax
   • Available for upload, download, and delete operations

📈 Status Bar:
   • Bottom-left: Current operation status
   • Bottom-right: Session configuration indicator
     ✅ Configured - Ready to use
     ❌ Not Configured - Setup required

💬 Output Console:
   • Real-time output from JFrog CLI
   • Success/error messages
   • Detailed operation logs"""
        
        progress_label = ttk.Label(progress_frame, text=progress_text, justify='left')
        progress_label.pack(anchor='w')
        
        # Security Best Practices
        security_frame = ttk.LabelFrame(container, text="🔒 Security Best Practices", padding="15")
        security_frame.pack(fill='x', pady=(0, 15))
        
        security_text = """✅ DO:
   • Enter credentials at the start of each session
   • Use "Clear Session" when switching users
   • Keep your access token confidential
   • Close application when finished
   • Use strong, unique access tokens

❌ DON'T:
   • Share your access token with others
   • Leave application open and unattended
   • Use the same token for multiple purposes
   • Take screenshots showing credentials

🛡️ How We Protect You:
   • Credentials stored in memory only (session-based)
   • No disk storage of sensitive information
   • Configuration cleared on application close
   • Access token masked in UI (shown as ****)
   • Automatic session timeout protection"""
        
        security_label = ttk.Label(security_frame, text=security_text, justify='left',
                                  foreground='blue')
        security_label.pack(anchor='w')
        
        # Tips & Best Practices
        tips_frame = ttk.LabelFrame(container, text="💡 Tips & Best Practices", padding="15")
        tips_frame.pack(fill='x', pady=(0, 15))
        
        tips_text = """• Always configure session before performing operations
• Use scan with filters to find specific artifacts quickly
• Export scan results for offline reference and documentation
• Check command viewer to understand CLI operations
• Monitor progress bar for long-running operations
• Use "Dry Run" before any delete operation
• Check the log file (artifactory_manager.log) for detailed information
• Repository paths should use forward slashes (/) not backslashes (\\)
• Test connection after configuring to verify credentials"""
        
        tips_label = ttk.Label(tips_frame, text=tips_text, justify='left')
        tips_label.pack(anchor='w')
        
        # Troubleshooting
        troubleshooting_frame = ttk.LabelFrame(container, text="🔧 Troubleshooting", padding="15")
        troubleshooting_frame.pack(fill='x', pady=(0, 15))
        
        troubleshooting_text = """❌ "Not Configured" Error:
   • Go to Settings tab
   • Enter all required credentials
   • Click "Configure Session"
   • Wait for success confirmation

❌ Connection Failed:
   • Verify Artifactory URL is correct
   • Check access token is valid and not expired
   • Ensure network connectivity
   • Try "Test Connection" button

❌ Scan Returns No Results:
   • Check repository path exists
   • Verify you have read permissions
   • Try removing filters temporarily
   • Increase max depth if needed

❌ Upload/Download Failed:
   • Ensure session is configured
   • Verify repository path format
   • Check you have proper permissions
   • Review command output for details

❌ Export Fails:
   • Run scan successfully first
   • Ensure you have write permissions
   • Check destination folder exists"""
        
        troubleshooting_label = ttk.Label(troubleshooting_frame, text=troubleshooting_text, justify='left')
        troubleshooting_label.pack(anchor='w')
        
        # Footer
        footer_frame = ttk.Frame(container)
        footer_frame.pack(fill='x', pady=(20, 0))
        
        footer_text = """━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Version 2.0 - Enhanced security, advanced filtering, and improved UX
This tool simplifies JFrog Artifactory operations with an intuitive interface.

For support or feature requests, contact the author.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
        
        footer_label = ttk.Label(footer_frame, text=footer_text, justify='center', 
                                font=('Arial', 9, 'italic'))
        footer_label.pack()
        
        # Pack canvas and scrollbar
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Bind mouse wheel for scrolling
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        canvas.bind_all("<MouseWheel>", on_mousewheel)
    
    def check_cli_installation(self):
        """Check JFrog CLI installation status"""
        if self.cli_manager.is_installed():
            try:
                result = subprocess.run(
                    [str(self.cli_manager.cli_executable), "--version"],
                    capture_output=True, text=True
                )
                version = result.stdout.strip()
                self.cli_status_var.set(f"✅ JFrog CLI installed: {version}")
                if not self.session_configured:
                    self.status_var.set("Ready - Please configure credentials")
            except Exception as e:
                self.cli_status_var.set(f"❌ Error checking CLI: {e}")
        else:
            self.cli_status_var.set("❌ JFrog CLI not installed")
            self.status_var.set("Please install JFrog CLI")
    
    def install_cli(self):
        """Install JFrog CLI"""
        self.status_var.set("Installing JFrog CLI...")
        
        def install():
            success = self.cli_manager.install()
            self.root.after(0, lambda: self.install_complete(success))
        
        threading.Thread(target=install, daemon=True).start()
    
    def install_complete(self, success):
        """Handle CLI installation completion"""
        if success:
            messagebox.showinfo("Success", "JFrog CLI installed successfully!")
            self.check_cli_installation()
        else:
            messagebox.showerror("Error", "Failed to install JFrog CLI. Check logs.")
            self.status_var.set("Failed to install JFrog CLI")
    
    def save_configuration(self):
        """Save and configure Artifactory connection (session only)"""
        if not self.cli_manager.is_installed():
            messagebox.showerror("Error", "JFrog CLI is not installed. Please install it first.")
            return
        
        server_id = self.server_id_var.get()
        url = self.url_var.get()
        token = self.token_var.get()
        user = self.user_var.get().strip()  # Optional
        
        # Only require server_id, url, and token
        if not all([server_id, url, token]):
            messagebox.showerror("Error", "Please fill in Server ID, URL, and Access Token (username is optional)")
            return
        
        self.status_var.set("Configuring session...")
        
        def configure():
            # Pass user only if provided
            success = self.cli_manager.configure_server(
                server_id, url, token, user if user else None
            )
            if success:
                self.artifactory_manager.set_credentials(url, token)
            self.root.after(0, lambda: self.configure_complete(success))
        
        threading.Thread(target=configure, daemon=True).start()
    
    def configure_complete(self, success):
        """Handle configuration completion"""
        if success:
            self.session_configured = True
            self.session_var.set("✅ Configured")
            messagebox.showinfo("Success", 
                              "Session configured successfully!\n\n"
                              "Note: Configuration is session-only and will be cleared when you close the application.")
            self.status_var.set("Session configured - Ready to use")
        else:
            self.session_configured = False
            self.session_var.set("❌ Not Configured")
            messagebox.showerror("Error", "Failed to configure session. Check logs.")
            self.status_var.set("Configuration failed")
    
    def clear_session(self):
        """Clear session configuration"""
        if not self.session_configured:
            messagebox.showinfo("Info", "No active session to clear.")
            return
        
        response = messagebox.askyesno(
            "Clear Session",
            "Are you sure you want to clear the current session?\n\n"
            "This will remove all credentials from memory."
        )
        
        if response:
            server_id = self.server_id_var.get()
            self.cli_manager.remove_server(server_id)
            self.artifactory_manager.set_credentials("", "")
            self.session_configured = False
            self.session_var.set("❌ Not Configured")
            
            # Clear token field
            self.token_var.set("")
            
            self.status_var.set("Session cleared - Please configure credentials")
            messagebox.showinfo("Success", "Session cleared successfully.")
    
    def test_connection(self):
        """Test Artifactory connection"""
        url = self.url_var.get()
        token = self.token_var.get()
        
        if not all([url, token]):
            messagebox.showerror("Error", "Please fill in URL and Access Token")
            return
        
        self.status_var.set("Testing connection...")
        
        def test():
            try:
                headers = {"Authorization": f"Bearer {token}"}
                response = requests.get(f"{url.rstrip('/')}/api/system/ping", 
                                      headers=headers, timeout=10)
                success = response.status_code == 200
                self.root.after(0, lambda: self.test_complete(success))
            except Exception as e:
                self.root.after(0, lambda: self.test_complete(False, str(e)))
        
        threading.Thread(target=test, daemon=True).start()
    
    def test_complete(self, success, error=None):
        """Handle connection test completion"""
        if success:
            messagebox.showinfo("Success", "Connection successful!")
            self.status_var.set("Connection OK")
        else:
            msg = f"Connection failed: {error}" if error else "Connection failed"
            messagebox.showerror("Error", msg)
            self.status_var.set("Connection failed")
    
    def check_session_configured(self):
        """Check if session is configured"""
        if not self.session_configured:
            messagebox.showerror(
                "Not Configured",
                "Please configure your session first in the Settings tab.\n\n"
                "For security, credentials are not saved and must be entered each time."
            )
            return False
        return True
    
    def browse_upload_folder(self):
        """Browse for upload folder"""
        folder = filedialog.askdirectory()
        if folder:
            self.upload_local_var.set(folder)
    
    def browse_upload_file(self):
        """Browse for upload file"""
        file = filedialog.askopenfilename()
        if file:
            self.upload_local_var.set(file)
    
    def browse_download_folder(self):
        """Browse for download folder"""
        folder = filedialog.askdirectory()
        if folder:
            self.download_local_var.set(folder)
    
    def append_to_progress(self, text_widget, message):
        """Append message to progress text widget"""
        text_widget.config(state='normal')
        text_widget.insert(tk.END, message)
        text_widget.see(tk.END)
        text_widget.config(state='disabled')
    
    def set_command_text(self, text_widget, command):
        """Set command text"""
        text_widget.config(state='normal')
        text_widget.delete(1.0, tk.END)
        text_widget.insert(1.0, command)
        text_widget.config(state='disabled')
    
    def xp_animate(self, progress_bar, prefix):
        """Windows XP-style segmented animation"""
        if not getattr(self, f"{prefix}_xp_active", False):
            return
        
        # Get current position
        value = getattr(self, f"{prefix}_xp_value", 0)
        
        # Move forward by segment size (Windows XP uses ~15% segments)
        value += 3  # 3% per frame for smooth segment movement
        
        # Reset at end and loop
        if value > 100:
            value = 0
        
        # Update progress bar
        progress_bar['value'] = value
        
        # Save state
        setattr(self, f"{prefix}_xp_value", value)
        
        # Schedule next frame (100ms for classic XP speed)
        if getattr(self, f"{prefix}_xp_active", False):
            self.root.after(100, lambda: self.xp_animate(progress_bar, prefix))
    
    def start_xp_animation(self, progress_bar, prefix):
        """Start Windows XP animation"""
        setattr(self, f"{prefix}_xp_active", True)
        setattr(self, f"{prefix}_xp_value", 0)
        progress_bar['value'] = 0
        self.xp_animate(progress_bar, prefix)
    
    def stop_xp_animation(self, progress_bar, prefix):
        """Stop Windows XP animation"""
        setattr(self, f"{prefix}_xp_active", False)
        progress_bar['value'] = 0
    
    def start_upload(self):
        """Start file upload"""
        if not self.check_session_configured():
            return
        
        local_path = self.upload_local_var.get()
        repo_path = self.upload_repo_var.get()
        server_id = self.server_id_var.get()
        
        if not all([local_path, repo_path, server_id]):
            messagebox.showerror("Error", "Please fill in all required fields")
            return
        
        if not os.path.exists(local_path):
            messagebox.showerror("Error", "Local path does not exist")
            return
        
        self.upload_progress.config(state='normal')
        self.upload_progress.delete(1.0, tk.END)
        self.upload_progress.config(state='disabled')
        
        self.start_xp_animation(self.upload_progress_bar, "upload")
        self.status_var.set("Uploading...")
        
        def upload():
            result = self.artifactory_manager.upload_files(
                local_path, repo_path, server_id,
                flat=self.upload_flat_var.get(),
                recursive=self.upload_recursive_var.get(),
                progress_callback=lambda msg: self.root.after(
                    0, lambda: self.append_to_progress(self.upload_progress, msg)),
                command_callback=lambda cmd: self.root.after(
                    0, lambda: self.set_command_text(self.upload_command, cmd))
            )
            self.root.after(0, lambda: self.upload_complete(result))
        
        threading.Thread(target=upload, daemon=True).start()
    
    def upload_complete(self, result):
        """Handle upload completion"""
        self.stop_xp_animation(self.upload_progress_bar, "upload")
        
        if result["success"]:
            messagebox.showinfo("Success", "Upload completed successfully!")
            self.status_var.set("Upload completed")
        else:
            messagebox.showerror("Error", f"Upload failed: {result.get('error', 'Unknown error')}")
            self.status_var.set("Upload failed")
    
    def start_scan(self):
        """Start repository scan"""
        if not self.check_session_configured():
            return
        
        repo_path = self.scan_repo_var.get()
        max_depth = self.scan_depth_var.get()
        name_filter = self.scan_name_filter_var.get()
        file_filter = self.scan_file_filter_var.get()
        
        if not repo_path:
            messagebox.showerror("Error", "Please enter repository path")
            return
        
        # Clear existing tree
        for item in self.scan_tree.get_children():
            self.scan_tree.delete(item)
        
        self.start_xp_animation(self.scan_progress_bar, "scan")
        self.status_var.set("Scanning repository...")
        
        def scan():
            result = self.artifactory_manager.scan_repository(
                repo_path, max_depth, name_filter, file_filter)
            self.root.after(0, lambda: self.scan_complete(result))
        
        threading.Thread(target=scan, daemon=True).start()
    
    def scan_complete(self, result):
        """Handle scan completion"""
        self.stop_xp_animation(self.scan_progress_bar, "scan")
        
        if result["success"]:
            self.last_scan_tree = result["tree"]
            self.populate_tree(result["tree"])
            self.status_var.set("Scan completed")
            messagebox.showinfo("Success", "Repository scanned successfully!")
        else:
            messagebox.showerror("Error", f"Scan failed: {result.get('error', 'Unknown error')}")
            self.status_var.set("Scan failed")
    
    def populate_tree(self, tree_data, parent=''):
        """Populate treeview with scan results"""
        icon = "📁" if tree_data["type"] == "folder" else "📄"
        name = f"{icon} {tree_data['name']}"
        
        item = self.scan_tree.insert(
            parent, 'end', text=name,
            values=(tree_data["type"], tree_data.get("path", ""))
        )
        
        for child in tree_data.get("children", []):
            self.populate_tree(child, item)
    
    def export_scan_results(self):
        """Export scan results to text file"""
        if not self.last_scan_tree:
            messagebox.showerror("Error", "No scan results to export. Please run a scan first.")
            return
        
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=f"artifactory_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )
        
        if not file_path:
            return
        
        try:
            tree_text = self.artifactory_manager.export_tree_to_text(self.last_scan_tree)
            
            # Add header
            header = f"""JFrog Artifactory Scan Results
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Repository: {self.scan_repo_var.get()}
Max Depth: {self.scan_depth_var.get()}
Name Filter: {self.scan_name_filter_var.get() or 'None'}
File Filter: {self.scan_file_filter_var.get() or 'None'}

{'='*80}

"""
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(header)
                f.write(tree_text)
            
            messagebox.showinfo("Success", f"Scan results exported to:\n{file_path}")
            self.status_var.set("Export completed")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export: {str(e)}")
            self.status_var.set("Export failed")
    
    def clear_scan_results(self):
        """Clear scan results"""
        for item in self.scan_tree.get_children():
            self.scan_tree.delete(item)
        self.last_scan_tree = None
        self.status_var.set("Scan results cleared")
    
    def start_download(self):
        """Start file download"""
        if not self.check_session_configured():
            return
        
        repo_path = self.download_repo_var.get()
        local_path = self.download_local_var.get()
        server_id = self.server_id_var.get()
        
        if not all([repo_path, local_path, server_id]):
            messagebox.showerror("Error", "Please fill in all required fields")
            return
        
        self.download_progress.config(state='normal')
        self.download_progress.delete(1.0, tk.END)
        self.download_progress.config(state='disabled')
        
        self.start_xp_animation(self.download_progress_bar, "download")
        self.status_var.set("Downloading...")
        
        def download():
            result = self.artifactory_manager.download_files(
                repo_path, local_path, server_id,
                flat=self.download_flat_var.get(),
                recursive=self.download_recursive_var.get(),
                progress_callback=lambda msg: self.root.after(
                    0, lambda: self.append_to_progress(self.download_progress, msg)),
                command_callback=lambda cmd: self.root.after(
                    0, lambda: self.set_command_text(self.download_command, cmd))
            )
            self.root.after(0, lambda: self.download_complete(result))
        
        threading.Thread(target=download, daemon=True).start()
    
    def download_complete(self, result):
        """Handle download completion"""
        self.stop_xp_animation(self.download_progress_bar, "download")
        
        if result["success"]:
            msg = f"Download completed successfully!\nFiles saved to: {result.get('path', '')}"
            messagebox.showinfo("Success", msg)
            self.status_var.set("Download completed")
        else:
            messagebox.showerror("Error", f"Download failed: {result.get('error', 'Unknown error')}")
            self.status_var.set("Download failed")
    
    def start_delete_dryrun(self):
        """Start delete dry run"""
        if not self.check_session_configured():
            return
        
        repo_path = self.delete_repo_var.get()
        server_id = self.server_id_var.get()
        
        if not repo_path:
            messagebox.showerror("Error", "Please enter repository path to delete")
            return
        
        if not server_id:
            messagebox.showerror("Error", "Please configure server settings first")
            return
        
        self.delete_progress.config(state='normal')
        self.delete_progress.delete(1.0, tk.END)
        self.delete_progress.config(state='disabled')
        
        self.start_xp_animation(self.delete_progress_bar, "delete")
        self.status_var.set("Running dry-run...")
        
        def delete_dryrun():
            result = self.artifactory_manager.delete_files(
                repo_path, server_id,
                recursive=self.delete_recursive_var.get(),
                dry_run=True,
                progress_callback=lambda msg: self.root.after(
                    0, lambda: self.append_to_progress(self.delete_progress, msg)),
                command_callback=lambda cmd: self.root.after(
                    0, lambda: self.set_command_text(self.delete_command, cmd))
            )
            self.root.after(0, lambda: self.delete_dryrun_complete(result))
        
        threading.Thread(target=delete_dryrun, daemon=True).start()
    
    def delete_dryrun_complete(self, result):
        """Handle delete dry run completion"""
        self.stop_xp_animation(self.delete_progress_bar, "delete")
        
        if result["success"]:
            messagebox.showinfo("Dry Run Complete", 
                              "Dry run completed successfully!\n\n"
                              "Review the output to see what would be deleted.\n"
                              "If correct, uncheck 'Dry Run' and run deletion.")
            self.status_var.set("Dry run completed")
        else:
            messagebox.showerror("Error", f"Dry run failed: {result.get('error', 'Unknown error')}")
            self.status_var.set("Dry run failed")
    
    def start_delete(self):
        """Start file deletion"""
        if not self.check_session_configured():
            return
        
        repo_path = self.delete_repo_var.get()
        confirm_path = self.delete_confirm_var.get()
        server_id = self.server_id_var.get()
        
        if not repo_path:
            messagebox.showerror("Error", "Please enter repository path to delete")
            return
        
        if not server_id:
            messagebox.showerror("Error", "Please configure server settings first")
            return
        
        # Check if dry run is enabled
        if self.delete_dryrun_var.get():
            messagebox.showwarning("Dry Run Mode", 
                                 "Dry Run mode is enabled. This will only preview the deletion.\n\n"
                                 "Uncheck 'Dry Run' option to perform actual deletion.")
            self.start_delete_dryrun()
            return
        
        # Require confirmation for actual deletion
        if repo_path != confirm_path:
            messagebox.showerror("Confirmation Failed", 
                               "Path confirmation does not match!\n\n"
                               "Please type the exact path in the confirmation field.")
            return
        
        # Final confirmation dialog
        response = messagebox.askyesno(
            "⚠️ Confirm Deletion",
            f"Are you absolutely sure you want to delete:\n\n{repo_path}\n\n"
            f"Recursive: {self.delete_recursive_var.get()}\n\n"
            "This action CANNOT be undone!",
            icon='warning'
        )
        
        if not response:
            return
        
        self.delete_progress.config(state='normal')
        self.delete_progress.delete(1.0, tk.END)
        self.delete_progress.config(state='disabled')
        
        self.start_xp_animation(self.delete_progress_bar, "delete")
        self.status_var.set("Deleting files...")
        
        def delete():
            result = self.artifactory_manager.delete_files(
                repo_path, server_id,
                recursive=self.delete_recursive_var.get(),
                dry_run=False,
                progress_callback=lambda msg: self.root.after(
                    0, lambda: self.append_to_progress(self.delete_progress, msg)),
                command_callback=lambda cmd: self.root.after(
                    0, lambda: self.set_command_text(self.delete_command, cmd))
            )
            self.root.after(0, lambda: self.delete_complete(result))
        
        threading.Thread(target=delete, daemon=True).start()
    
    def delete_complete(self, result):
        """Handle delete completion"""
        self.stop_xp_animation(self.delete_progress_bar, "delete")
        
        if result["success"]:
            messagebox.showinfo("Success", "Files deleted successfully!")
            self.status_var.set("Deletion completed")
            # Clear confirmation field
            self.delete_confirm_var.set("")
        else:
            messagebox.showerror("Error", f"Deletion failed: {result.get('error', 'Unknown error')}")
            self.status_var.set("Deletion failed")


def main():
    """Main entry point"""
    root = tk.Tk()
    app = ArtifactoryGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
