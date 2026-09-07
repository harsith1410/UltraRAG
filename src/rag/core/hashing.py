import hashlib

def get_file_hash(file_path):
    hasher =hashlib.md5()
    with open(file_path,'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)

    return hasher.hexdigest()