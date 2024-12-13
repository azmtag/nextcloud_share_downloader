import os
import sys
import shutil
import fnmatch
import itertools
import argparse
import getpass
import requests
import urllib.parse
from xml.dom import minidom
from tqdm import tqdm
    

PROPFIND_REQUEST = '''<?xml version="1.0" encoding="UTF-8"?>
<d:propfind xmlns:d="DAV:">
    <d:prop xmlns:oc="http://owncloud.org/ns">
        <d:getlastmodified/>
        <d:getcontentlength/>
        <d:getcontenttype/>
    </d:prop>
</d:propfind>'''

CODE_SUCCESS  = 207
LEN_PATH_PREF = len('/public.php/webdav')


def parse_args():
    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('url')
    parser.add_argument('-y', '--yes', help="Sets any confirmation values to 'yes' automatically.", action="store_true", default=False)
    parser.add_argument('-p', '--password', help="Specify the password for a protected share.", default='')
    parser.add_argument('--password-prompt', help="Prompt for the password for a protected share.", action="store_true", default=False, dest='prompt')
    parser.add_argument('-o', '--output', help="Output dir.", default='.')
    parser.add_argument('-R', '--resume', help="Resume download.", action="store_true", default=False)
    parser.add_argument('-g', '--glob', help="Glob pattern for filtering files by their name.", action='append')
    parsed_args = parser.parse_args()
    return parsed_args


def query_yes_no(question, default="yes"):
    """Ask a yes/no question via raw_input() and return their answer.

    "question" is a string that is presented to the user.
    "default" is the presumed answer if the user just hits <Enter>.
            It must be "yes" (the default), "no" or None (meaning
            an answer is required of the user).

    The "answer" return value is True for "yes" or False for "no".

    Source: https://stackoverflow.com/a/3041990
    """
    valid = {"yes": True, "y": True, "ye": True, "no": False, "n": False}
    if default is None:
        prompt = " [y/n] "
    elif default == "yes":
        prompt = " [Y/n] "
    elif default == "no":
        prompt = " [y/N] "
    else:
        raise ValueError("invalid default answer: '%s'" % default)

    while True:
        sys.stdout.write(question + prompt)
        choice = input().lower()
        if default is not None and choice == "":
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            sys.stdout.write("Please respond with 'yes' or 'no' " "(or 'y' or 'n').\n")


def path_fmt(path, desc_len=200, desc_pref=''):
    if len(path) < desc_len:
        return desc_pref + path.ljust(desc_len)
    return f'{desc_pref}...{path[-desc_len + 3:]}'


def sizeof_fmt(num, suffix="B"):
    for unit in ("", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"):
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Yi{suffix}"


def parse_propfind_response(text):
    dom = minidom.parseString(text.encode('ascii', 'xmlcharrefreplace'))
    res = []
    for response in dom.getElementsByTagName('d:response'):
        item = {
            'path': response.getElementsByTagName(f'd:href')[0].firstChild.data[LEN_PATH_PREF:],
        }
        for field in ['lastmodified', 'contentlength', 'contenttype']:
            node = response.getElementsByTagName(f'd:get{field}')[0].firstChild
            if node:
                item[field] = node.data
        if 'contentlength' in item:
            item['contentlength'] = int(item['contentlength'])
        res.append(item)
    return res


def list_dir(session, host, path):
    url = f'{host}/public.php/webdav/{path}'
    r = session.request(method='PROPFIND', url=url, data=PROPFIND_REQUEST)
    if r.status_code != CODE_SUCCESS:
        raise RuntimeError(f'Unexpected response from {url}\n Status code: {r.status_code}\n Message:\n{r.text}')
    
    # the first element is the current dir specified by `path`, skip it 
    return parse_propfind_response(r.text)[1:]


def walk_dir(session, host, path):
    files = []
    for x in list_dir(session, host, path):
        if x['path'].endswith('/'):
            files += walk_dir(session, host, x['path'])
        else:
            files.append(x)
    return files


def check_dir_not_empty(path):
    return os.path.isdir(path) and os.listdir(path)


def glob_filter(path, globs):
    for g in globs:
        if fnmatch.fnmatch(path, g):
            return True
    return False
    

def check_files(files):
    new = []
    existing = []
    mismatched = []
    for x in files:
        if os.path.isfile(x['dest']):
            x['filesize'] = os.path.getsize(x['dest'])
            if x['filesize'] == x['contentlength']:
                existing.append(x)
            else:
                mismatched.append(x)
        else:
            new.append(x)
    return new, mismatched, existing


def get_file_lists(session, host_url, path, args):
    files = sorted(walk_dir(session, host_url, path), key=lambda x: x['path'])
    
    for x in files:
        x['dest'] = urllib.parse.unquote(os.path.join(args.output, x['path'][1:]))

    if args.glob:
        print('Filtering by matching file paths to:', args.glob)
        files = [x for x in files if glob_filter(x['dest'], args.glob)]
    
    if check_dir_not_empty(args.output):
        new_files, mismatched, existing = check_files(files)
    else:
        new_files, mismatched, existing = files, [], []

    return new_files, mismatched, existing


def download_file(session, host, path_share, path_out, desc_len=100, desc_pref=''):
    url = f'{host}/public.php/webdav/{path_share}'
    os.makedirs(os.path.dirname(path_out), exist_ok=True)
    
    response = session.get(url, stream=True)
    total_size = int(response.headers.get("content-length", 0))
    block_size = 1024

    with tqdm(total=total_size, unit="B", unit_scale=True, desc=path_fmt(path_share, desc_len=desc_len, desc_pref=desc_pref)) as progress_bar:
        with open(path_out, "wb") as file:
            for data in response.iter_content(block_size):
                progress_bar.update(len(data))
                file.write(data)

    if total_size != 0 and progress_bar.n != total_size:
        raise RuntimeError(f"Could not download file: {url}")


def print_share_contents(new_files, mismatched, existing, path_len=100):
    if existing:
        print('\nExisting files:\n---------------')
        for x in existing:
            print(f"{path_fmt(x['path'], desc_len=path_len)} {sizeof_fmt(x['contentlength']):<12} {x['lastmodified']:<34} {x['contenttype']:<40}")

    if new_files:
        print('\nNew files:\n----------')
        for x in new_files:
            print(f"{path_fmt(x['path'], desc_len=path_len)} {sizeof_fmt(x['contentlength']):<12} {x['lastmodified']:<34} {x['contenttype']:<40}")
    
    if mismatched:
        print('\nFiles with unexpected size:\n---------------------------')
        for x in mismatched:
            size_str = f"{sizeof_fmt(x['filesize'])} / {sizeof_fmt(x['contentlength'])}"
            print(f"{path_fmt(x['path'], desc_len=path_len-8)} {size_str:<20} {x['lastmodified']:<34} {x['contenttype']:<40}")
    print()


def main():
    args = parse_args()

    if check_dir_not_empty(args.output) and (not args.resume):
        print('Output dir is not empty. Specify `--resume` if you want to resume download. Exiting.')
        return

    n_col = max(shutil.get_terminal_size((160, 20)).columns, 160)
    desc_len = n_col - 100

    host_url = args.url.split('/s/')[0].split('/index.php')[0]
    token = args.url.rsplit('/', 1)[-1].split('?')[0]
    path  = args.url.rsplit('=', 1)[-1].replace('%2F', '/') + '/' if '?' in args.url else '/'

    pw = args.password
    if args.prompt:
        pw = getpass.getpass()

    s = requests.Session()
    s.auth = token, pw

    print('Reading share contents.')
    new_files, mismatched, existing = get_file_lists(s, host_url, path, args)

    print_share_contents(new_files, mismatched, existing, path_len=desc_len)
    
    total = sum(x['contentlength'] for x in itertools.chain(new_files, mismatched))
    print(f'{len(new_files)} new file(s) will be downloaded and {len(mismatched)} overwritten. Total size: {sizeof_fmt(total)}')

    n_download = len(new_files) + len(mismatched)
    if n_download == 0:
        print('Nothing to download. Exiting.')
        return

    if (not args.yes) and (not query_yes_no(f'Proceed ([y]/n)?', default="yes")):
        print('Aborted.')
        return

    for i, x in enumerate(itertools.chain(mismatched, new_files), start=1):
        download_file(s, host_url, x['path'], x['dest'], desc_len=desc_len, desc_pref=f'[{i}/{n_download}] ')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'ERROR:', e)
        print('Exiting.')