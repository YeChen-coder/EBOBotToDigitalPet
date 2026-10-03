"""Register supplied parent photos in this project's local Frigate only."""
import argparse
import io
import json
import mimetypes
import uuid
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from PIL import Image
from config import Config


def enroll(config, user_id, photos, opener=urlopen):
    profile = config.profile(user_id)
    images = []
    for path in photos:
        path = Path(path)
        if not path.is_file() or path.stat().st_size > 12*1024*1024:
            raise ValueError('Photo must be a file no larger than 12 MiB')
        raw = path.read_bytes()
        with Image.open(io.BytesIO(raw)) as image:
            image.verify()
        images.append((path.name, raw, mimetypes.guess_type(path.name)[0] or 'image/jpeg'))
    if not images:
        raise ValueError('Provide at least one photo')
    base = config.frigate_url.rstrip('/') + '/api/faces/' + quote(profile.face_name, safe='')
    with opener(Request(base+'/create', data=b'', method='POST'),timeout=30) as response:
        # Frigate 0.18 create returns success:false even when its HTTP status is 200.
        if response.status != 200:
            raise ValueError('Frigate could not create the face name')
    count = 0
    for name, raw, mime in images:
        boundary = 'ebo_' + uuid.uuid4().hex
        # Filename is a fixed ASCII value; private host paths never enter the upload.
        payload = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="face.jpg"\r\nContent-Type: {mime}\r\n\r\n'.encode('ascii')
            + raw + f'\r\n--{boundary}--\r\n'.encode('ascii'))
        with opener(Request(base+'/register',data=payload,method='POST',headers={'Content-Type':'multipart/form-data; boundary='+boundary}),timeout=60) as response:
            result = json.load(response)
            if response.status != 200 or result.get('success') is not True:
                raise ValueError('Frigate could not recognize a usable face in a supplied photo')
        count += 1
        print(f'Registered {count}/{len(images)} for {profile.display_name}',flush=True)
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user',required=True)
    parser.add_argument('--photo-directory',type=Path,required=True)
    args = parser.parse_args()
    photos = sorted(p for p in args.photo_directory.iterdir() if p.is_file() and p.suffix.lower() in {'.jpg','.jpeg','.png','.webp'})
    enroll(Config.from_env(),args.user,photos)


if __name__ == '__main__':
    main()
