# Nextcloud share downloader

A script for recursively downloading entire NextCloud shares from the command line. The script is loosely based on [aertslab/nextcloud_share_url_downloader](https://github.com/aertslab/nextcloud_share_url_downloader). Tested in Linux and macOS and Python 3.9.

## Usage
```
ncdownloader.py [-h] [-y] [-p PASSWORD] [--password-prompt] [-o OUTPUT] [-R] [-g GLOB] url

positional arguments:
  url

optional arguments:
  -h, --help            show this help message and exit
  -y, --yes             Sets any confirmation values to 'yes' automatically.
  -p PASSWORD, --password PASSWORD
                        Specify the password for a protected share.
  --password-prompt     Prompt for the password for a protected share.
  -o OUTPUT, --output OUTPUT
                        Output dir [default: current directory].
  -R, --resume          Resume download.
  -g GLOB, --glob GLOB  Glob pattern for filtering files by their name.
```

## Examples
### Download a share recursively
```
# Download all files from a share
./ncdownloader.py -o path_to_download_to "https://nextcloud.example.com/index.php/s/c56Ci4EpLnjj9xT"

# Download all files from a subdirectory
./ncdownloader.py -o path_to_download_to "https://nextcloud.example.com/index.php/s/c56Ci4EpLnjj9xT?path=subdir"
```
### Download files matching specified glob(s)
```
./ncdownloader.py -o path_to_download_to --glob "*.txt" --glob "*_1.*" "https://nextcloud.example.com/index.php/s/c56Ci4EpLnjj9xT"
```
will download, e.g., `/example.txt`, `/subdir/example.txt`, `/subdir/file_1.gz`, `/subdir_1.2/subdir/file.gz`.
