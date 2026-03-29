# JFrog Artifactory Manager

A cross-platform GUI tool for managing JFrog Artifactory operations. Built with Python and Tkinter, wrapping the JFrog CLI with an intuitive interface.

## Features

- **Upload** — transfer files and folders to Artifactory with flat/recursive options
- **Scan** — browse repository structure with name and file filters, wildcard support, adjustable depth, and export to text
- **Download** — pull artifacts to a local directory
- **Delete** — remove artifacts with dry-run preview and path confirmation safety
- **Auto CLI Install** — downloads and configures JFrog CLI automatically
- **Session-Only Credentials** — access tokens are kept in memory only, never written to disk
- **Command Viewer** — shows the exact JFrog CLI command being executed for each operation
- **Cross-Platform** — works on Windows, Linux, and macOS

## Requirements

- Python 3.6+
- Tkinter (usually included with Python)
- `requests` library

### Installing Dependencies

```bash
pip install requests
```

**Tkinter** is typically bundled with Python. If missing:

| Platform | Install Command |
|----------|----------------|
| Ubuntu/Debian | `sudo apt-get install python3-tk` |
| Fedora/RHEL | `sudo dnf install python3-tkinter` |
| Arch | `sudo pacman -S tk` |
| macOS (Homebrew) | `brew install python-tk` |
| Windows | Included by default; reinstall Python with "tcl/tk" option if missing |

JFrog CLI is **not** required beforehand — the app can install it for you from the Settings tab.

## Usage

```bash
python3 artifactory_manager.py
```

### Quick Start

1. **Settings tab** — click "Install JFrog CLI" if not already installed
2. **Settings tab** — enter your Artifactory URL, access token, and a server ID, then click "Configure Session"
3. **Test Connection** — verify credentials work
4. Use the **Upload**, **Scan**, **Download**, or **Delete** tabs as needed

### Tabs Overview

**Settings** — JFrog CLI installation, Artifactory URL/token configuration, connection test. Credentials are session-only and cleared on exit.

**Upload** — select a local file or folder, specify the target repository path, and upload. Supports flat structure and recursive options.

**Scan** — enter a repository path and scan its structure up to a configurable depth (1–10). Filter by name (`*test*`, `build*`) or file extension (`*.zip`, `*.log`). Export results to a text file.

**Download** — specify a repository path and local destination. Supports flat and recursive options.

**Delete** — enter a repository path to delete. Dry-run mode is enabled by default so you can preview what will be removed. Actual deletion requires typing the path again for confirmation, plus a final dialog.

### Example Paths

| Operation | Example Path |
|-----------|-------------|
| Upload | `my-repo/builds/v1.2.3/` |
| Scan | `my-repo/` |
| Download | `my-repo/builds/v1.2.3/release/` |
| Delete | `my-repo/builds/old-build/` |

## Security

Credentials (access tokens) are stored in memory for the current session only. Nothing is written to disk. Use "Clear Session" in Settings to wipe credentials from memory, or just close the app.

The tool also generates an `artifactory_manager.log` file in the working directory for debugging — this file does **not** contain credentials, but you may want to add it to `.gitignore`.

## Troubleshooting

**"Not Configured" error** — go to Settings, enter credentials, click "Configure Session".

**Connection failed** — check that the Artifactory URL is correct, the access token is valid/not expired, and you have network access.

**Scan returns no results** — verify the repository path exists, check permissions, try removing filters, or increase max depth.

**Upload/Download failed** — review the Command and Output panels for the exact error. Ensure the repository path uses forward slashes (`/`).

## License

MIT License — see [LICENSE](LICENSE) for details.

## Author

Created by Oleh Sharudin — [github.com/OlehSharudin](https://github.com/OlehSharudin)
