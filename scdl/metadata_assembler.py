from base64 import b64decode, b64encode
from dataclasses import dataclass
from functools import singledispatch
from typing import Optional, Union
from mutagen.id3 import TXXX
from PIL import Image
from io import BytesIO
from mutagen import (
    FileType,
    aiff,
    flac,
    id3,
    mp3,
    mp4,
    oggopus,
    oggspeex,
    oggtheora,
    wave,
)
import logging
import sys

logger = logging.getLogger('metadata_logger')
logger.setLevel(logging.INFO)

c_handler = logging.StreamHandler()
c_handler.setLevel(logging.DEBUG)

c_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
c_handler.setFormatter(c_formatter)

logger.addHandler(c_handler)

@dataclass(frozen=True)
class MetadataInfo:
    artist: str
    title: str
    description: Optional[str]
    genre: Optional[str]
    artwork_url: Optional[str]
    artwork_file: Optional[bytes]
    link: Optional[str]
    created_date: Optional[str]
    display_date: Optional[str]
    album_title: Optional[str]
    album_author: Optional[str]
    album_track_num: Optional[int]
    tags: Optional[str]
    uid: Optional[str]
    track_id: Optional[int]
    user_id: Optional[int]
    album_track_count: Optional[int]
    album_type: Optional[str]
    album_publish_date: Optional[str]
    album_display_date: Optional[str]
    album_created_date: Optional[str]
    album_release_date: Optional[str]
    album_link: Optional[str]

@singledispatch
def assemble_metadata(file: FileType, meta: MetadataInfo) -> None:
    raise NotImplementedError("Metadata assembly not implemented for this file type")

def _get_flac_pic(image_bytes: bytes, meta: MetadataInfo, mime_type: Optional[str] = None) -> flac.Picture:
    """Prepare FLAC picture metadata."""
    if mime_type is None:
        mime_type = get_mime_type(image_bytes)
    pic = flac.Picture()
    pic.data = image_bytes
    pic.mime = mime_type
    pic.desc = meta.artwork_url if meta.artwork_url else None
    pic.type = id3.PictureType.COVER_FRONT
    return pic

def _get_apic(image_bytes: bytes, meta: MetadataInfo, mime_type: Optional[str] = None) -> id3.APIC:
    """Prepare APIC metadata for MP3."""
    if mime_type is None:
        mime_type = get_mime_type(image_bytes)
    return id3.APIC(
        encoding=3,
        mime=mime_type,
        type=3,
        desc=meta.artwork_url if meta.artwork_url else None,
        data=image_bytes,
    )

def _assemble_vorbis_tags(file: FileType, meta: MetadataInfo) -> None:
    """Assemble Vorbis comments for FLAC, OGG, and OPUS files."""
    file["Artist"] = meta.artist
    file["Title"] = meta.title
    file["Date"] = meta.created_date
    file["WWWArtist"] = meta.link
    if meta.genre:
        file["Genre"] = meta.genre
    if meta.tags:
        file["Tags"] = meta.tags
    if meta.album_title:
        file["Album"] = meta.album_title
    if meta.album_author:
        file["Albumartist"] = meta.album_author
    if meta.album_track_num is not None:
        file["Tracknumber"] = str(meta.album_track_num)
    if meta.description:
        file["Description"] = meta.description
    if meta.artwork_url:
        file["Artwork"] = meta.artwork_url
    if meta.display_date:
        file["ReleaseTime"] = meta.display_date
    if meta.uid:
        file["UID"] = meta.uid
    if meta.track_id:
        file["ID"] = str(meta.track_id)
    if meta.user_id:
        file["ID User"] = str(meta.user_id)
    if meta.album_type:
        file["RELEASETYPE"] = meta.album_type
    if meta.album_display_date is not None:
        file["Album Display Date"] = meta.album_display_date
    if meta.album_publish_date is not None:
        file["Album Publish Date"] = meta.album_publish_date
    if meta.album_created_date:
        file["Album Creation Date"] = meta.album_created_date
    if meta.album_release_date:
        file["Album Release Date"] = meta.album_release_date
    if meta.album_link:
        file["WWWAlbum"] = str(meta.album_link)  
    
def get_mime_type(image_bytes: bytes) -> str:
    """Get MIME type of an image from its bytes."""
    image = Image.open(BytesIO(image_bytes))
    mime_type = Image.MIME[image.format]
    return mime_type

def resize_image_if_needed(image: Image) -> (Image, bool):
    """Resize image if its dimensions are larger than 3000x3000."""
    max_dimension = 10000
    resized = False

    if image.width > max_dimension or image.height > max_dimension:
        resized = True
        logger.debug(f"Original image size: {image.size}")

        # Calculate the scaling factor to ensure the resized dimensions do not exceed max_dimension
        scaling_factor = min(max_dimension / image.width, max_dimension / image.height)
        new_size = (int(image.width * scaling_factor), int(image.height * scaling_factor))

        image = image.resize(new_size, Image.LANCZOS)
        logger.debug(f"Resized image size: {image.size}")

    return image, resized

def re_encode_cover_image(image_bytes: bytes) -> bytes:
    """Re-encode cover image to ensure it does not exceed 3MB in size."""
    max_data_size = 2.93 * 1024 * 1024  # 2.93MB in bytes
    mime_type = get_mime_type(image_bytes)
    
    original_data_size = len(image_bytes)
    logger.debug(f"Original image data size: {original_data_size} bytes")

    # If the original image data size is within the acceptable limit
    if original_data_size <= max_data_size:
        logger.debug("Image data size is within the acceptable limit. No resizing needed.")
        return image_bytes

    with Image.open(BytesIO(image_bytes)) as img:
        img, resized = resize_image_if_needed(img)
        
        buffer = BytesIO()
        quality = 100
        
        if mime_type == 'image/jpeg':
            if resized:
                quality = 85
            img.save(buffer, format='JPEG', quality=quality)
            logger.debug(f"Adjusted quality for JPEG: {quality}%")
        elif mime_type == 'image/png':
            logger.debug("Converting PNG to JPEG")
            img = img.convert("RGB")
            if resized:
                quality = 85
            img.save(buffer, format='JPEG', quality=quality)
            logger.debug(f"Adjusted quality for converted JPEG: {quality}%")
        else:
            raise ValueError(f"Unsupported MIME type: {mime_type}")

        # Ensure the final image data size does not exceed the limit
        resized_data_size = buffer.tell()
        while resized_data_size > max_data_size and quality > 10:
            logger.debug(f"Image data size after encoding: {resized_data_size} bytes. Further quality reduction needed.")
            buffer.seek(0)
            quality -= 1  # Reduce quality in steps
            buffer.truncate()  # Clear the buffer
            img.save(buffer, format='JPEG', quality=quality)
            resized_data_size = buffer.tell()
            logger.debug(f"Quality adjusted to: {quality}%")
        
        logger.debug(f"Final image data size: {resized_data_size} bytes")
        
        return buffer.getvalue()

@assemble_metadata.register(flac.FLAC)
def _(file: flac.FLAC, meta: MetadataInfo) -> None:
    _assemble_vorbis_tags(file, meta)

    if meta.artwork_file:
        logger.debug("Clearing existing artwork from FLAC file.")
        file.clear_pictures()  # Clear existing artwork
        file.add_picture(_get_flac_pic(meta.artwork_file, meta))
        logger.debug("Artwork added to FLAC file.")

@assemble_metadata.register(oggtheora.OggTheora)
@assemble_metadata.register(oggspeex.OggSpeex)
@assemble_metadata.register(oggopus.OggOpus)
def _(file: oggopus.OggOpus, meta: MetadataInfo) -> None:
    _assemble_vorbis_tags(file, meta)

    if meta.artwork_file:
        re_encoded_image = re_encode_cover_image(meta.artwork_file)
        pic = _get_flac_pic(re_encoded_image, meta).write()
        file["metadata_block_picture"] = b64encode(pic).decode()

@assemble_metadata.register(aiff.AIFF)
@assemble_metadata.register(mp3.MP3)
@assemble_metadata.register(wave.WAVE)
def _(file: Union[wave.WAVE, mp3.MP3], meta: MetadataInfo) -> None:
    if 'APIC' in file:
        logger.debug("Clearing existing artwork from MP3 file.")
        del file['APIC']

    file["TIT2"] = id3.TIT2(encoding=3, text=meta.title)
    file["TPE1"] = id3.TPE1(encoding=3, text=meta.artist)
    file["TDRC"] = id3.TDRC(encoding=3, text=meta.created_date)
    file["WOAR"] = id3.WOAR(encoding=3, url=meta.link)
    if meta.display_date:
        file["TDRL"] = id3.TDRL(encoding=3, text=meta.display_date)
    if meta.description:
        file["COMM"] = id3.COMM(encoding=3, lang="ENG", text=meta.description)
    if meta.genre:
        file["TCON"] = id3.TCON(encoding=3, text=meta.genre)
    if meta.album_title:
        file["TALB"] = id3.TALB(encoding=3, text=meta.album_title)
    if meta.album_author:
        file["TPE2"] = id3.TPE2(encoding=3, text=meta.album_author)
    if meta.album_track_num is not None:
        file["TRCK"] = id3.TRCK(encoding=3, text=str(meta.album_track_num))
    if meta.artwork_file:
        file["APIC"] = _get_apic(meta.artwork_file, meta)
    if meta.artwork_url:
        file["TXXX:Artwork"] = TXXX(encoding=3, desc='Artwork', text=str(meta.artwork_url))
    if meta.tags:
        file["TXXX:Tags"] = TXXX(encoding=3, desc='Tags', text=str(meta.tags))
    if meta.uid:
        file["TXXX:UID"] = TXXX(encoding=3, desc='UID', text=str(meta.uid))
    if meta.track_id:
        file["TXXX:ID"] = TXXX(encoding=3, desc='ID', text=str(meta.track_id))
    if meta.user_id:
        file["TXXX:ID User"] = TXXX(encoding=3, desc='ID User', text=str(meta.user_id))
    if meta.album_type:
        file["TXXX:ReleaseType"] = TXXX(encoding=3, desc='ReleaseType', text=meta.album_type)
    if meta.album_display_date is not None:
        file["TXXX:Album Display Date"] = TXXX(encoding=3, desc='Album Display Date', text=meta.album_display_date)
    if meta.album_publish_date is not None:
        file["TXXX:Album Publish Date"] = TXXX(encoding=3, desc='Album Publish Date', text=meta.album_publish_date)
    if meta.album_created_date:
        file["TXXX:Album Creation Date"] = TXXX(encoding=3, desc='Album Creation Date', text=meta.album_created_date)
    if meta.album_release_date:
        file["TXXX:Album Release Date"] = TXXX(encoding=3, desc='Album Release Date', text=meta.album_release_date)    
    if meta.album_link:
        file["TXXX:WWWAlbum"] = TXXX(encoding=3, desc='WWWAlbum', text=meta.album_link)         
    
@assemble_metadata.register(mp4.MP4)
def _(file: mp4.MP4, meta: MetadataInfo) -> None:
    if 'covr' in file:
        logger.debug("Clearing existing artwork from MP4 file.")
        del file['covr']
        
    file["\251ART"] = meta.artist
    file["\251nam"] = meta.title
    file["\251day"] = meta.created_date
    file["----:com.apple.iTunes:WWWArtist"] = meta.link.encode() if meta.link else None
    if meta.description:
        file["\251cmt"] = meta.description
    if meta.genre:
        file["\251gen"] = meta.genre
    if meta.tags:
        file["----:com.apple.iTunes:Tags"] = meta.tags.encode()
    if meta.album_title:
        file["\251alb"] = meta.album_title
    if meta.album_author:
        file["aART"] = meta.album_author
    if meta.album_track_num is not None:
        file["trkn"] = [(meta.album_track_num, 0)]  # MP4 expects a tuple for track numbers
    if meta.artwork_file:
        file["covr"] = [mp4.MP4Cover(meta.artwork_file)]
    if meta.artwork_url:
        file["----:com.apple.iTunes:Artwork"] = meta.artwork_url.encode()
    if meta.display_date:
        file["----:com.apple.iTunes:ReleaseTime"] = meta.display_date.encode() if meta.display_date else None
    if meta.uid:
        file["----:com.apple.iTunes:UID"] = meta.uid.encode()
    if meta.track_id:
        file["----:com.apple.iTunes:ID"] = str(meta.track_id).encode()
    if meta.user_id:
        file["----:com.apple.iTunes:ID User"] = str(meta.user_id).encode()
    if meta.album_type:
        file["----:com.apple.iTunes:ReleaseType"] = meta.album_type.encode()
    if meta.album_display_date:
        file["----:com.apple.iTunes:Album Display Date"] = meta.album_display_date.encode() if meta.album_display_date else None
    if meta.album_publish_date:
        file["----:com.apple.iTunes:Album Publish Date"] = meta.album_publish_date.encode() if meta.album_publish_date else None
    if meta.album_created_date:
        file["----:com.apple.iTunes:Album Creation Date"] = meta.album_created_date.encode() if meta.album_created_date else None
    if meta.album_release_date:
        file["----:com.apple.iTunes:Album Release Date"] = meta.album_release_date.encode() if meta.album_release_date else None
    if meta.album_link:
        file["----:com.apple.iTunes:WWWAlbum"] = meta.album_link.encode() if meta.album_link else None