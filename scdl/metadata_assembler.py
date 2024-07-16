from base64 import b64encode
from dataclasses import dataclass
from functools import singledispatch
from typing import Optional, Union
import scdl
from mutagen.id3 import TXXX

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

JPEG_MIME_TYPE: str = "image/jpeg"


@dataclass(frozen=True)
class MetadataInfo:
    artist: str
    title: str
    description: Optional[str]
    genre: Optional[str]
    artwork_url: Optional[str]
    artwork_jpeg: Optional[bytes]
    link: Optional[str]
    date: Optional[str]
    album_title: Optional[str]
    album_author: Optional[str]
    album_track_num: Optional[int]
    tags: Optional[str]


@singledispatch
def assemble_metadata(file: FileType, meta: MetadataInfo) -> None:  # noqa: ARG001
    raise NotImplementedError


def _get_flac_pic(jpeg_data: bytes, meta: MetadataInfo) -> flac.Picture:
    pic = flac.Picture()
    pic.data = jpeg_data
    pic.mime = JPEG_MIME_TYPE
    pic.desc = meta.artwork_url if meta.artwork_url else "Cover"
    pic.type = id3.PictureType.COVER_FRONT
    return pic


def _get_apic(jpeg_data: bytes, meta: MetadataInfo) -> id3.APIC:
    return id3.APIC(
        encoding=3,
        mime=JPEG_MIME_TYPE,
        type=3,
        desc=meta.artwork_url if meta.artwork_url else "Cover",
        data=jpeg_data,
    )


def _assemble_vorbis_tags(file: FileType, meta: MetadataInfo) -> None:
    file["Artist"] = meta.artist
    file["Title"] = meta.title
    file["Date"] = meta.date
    file["WWWArtist"] = meta.link
    if meta.genre:
        file["Genre"] = meta.genre
    if  meta.tags:
        file["Tags"] = meta.tags
    if meta.album_title:
        file["Album"] = meta.album_title
    if meta.album_author:
        file["AlbumArtist"] = meta.album_author
    if meta.album_track_num is not None:
        file["TrackNumber"] = str(meta.album_track_num)
    if meta.description:
        file["Description"] = meta.description
    if meta.artwork_url:
        file["Artwork"] = meta.artwork_url


@assemble_metadata.register(flac.FLAC)
def _(file: flac.FLAC, meta: MetadataInfo) -> None:
    _assemble_vorbis_tags(file, meta)

    if meta.artwork_jpeg:
        file.add_picture(_get_flac_pic(meta.artwork_jpeg, meta))


@assemble_metadata.register(oggtheora.OggTheora)
@assemble_metadata.register(oggspeex.OggSpeex)
@assemble_metadata.register(oggopus.OggOpus)
def _(file: oggopus.OggOpus, meta: MetadataInfo) -> None:
    _assemble_vorbis_tags(file, meta)

    if meta.artwork_jpeg:
        pic = _get_flac_pic(meta.artwork_jpeg, meta).write()
        file["metadata_block_picture"] = b64encode(pic).decode()


@assemble_metadata.register(aiff.AIFF)
@assemble_metadata.register(mp3.MP3)
@assemble_metadata.register(wave.WAVE)
def _(file: Union[wave.WAVE, mp3.MP3], meta: MetadataInfo) -> None:
    file["TIT2"] = id3.TIT2(encoding=3, text=meta.title)
    file["TPE1"] = id3.TPE1(encoding=3, text=meta.artist)
    file["TDRC"] = id3.TDRC(encoding=3, text=meta.date)
    file["WOAR"] = id3.WOAR(url=meta.link)
    if meta.description:
        file["COMM"] = id3.COMM(encoding=3, lang="ENG", text=meta.description)
    if meta.genre:
        file["TCON"] = id3.TCON(encoding=3, text=meta.genre)
    if meta.tags:
        file["TXXX:Tags"] = TXXX(encoding=3, desc=u'Tags', text=str(meta.tags))
    if meta.album_title:
        file["TALB"] = id3.TALB(encoding=3, text=meta.album_title)
    if meta.album_author:
        file["TPE2"] = id3.TPE2(encoding=3, text=meta.album_author)
    if meta.album_track_num is not None:
        file["TRCK"] = id3.TRCK(encoding=3, text=str(meta.album_track_num))
    if meta.artwork_jpeg:
        file["APIC"] = _get_apic(meta.artwork_jpeg, meta)
    if meta.artwork_url:
        file["TXXX:Artwork"] = TXXX(encoding=3, desc=u'Artwork', text=str(meta.artwork_url))
        

@assemble_metadata.register(mp4.MP4)
def _(file: mp4.MP4, meta: MetadataInfo) -> None:
    file["\251ART"] = meta.artist
    file["\251nam"] = meta.title
    file["\251day"] = meta.date
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
    if meta.artwork_jpeg:
        file["covr"] = [mp4.MP4Cover(meta.artwork_jpeg)]
    if meta.artwork_url:
        file["----:com.apple.iTunes:Artwork"] = meta.artwork_url.encode()
