from datetime import datetime
from tempfile import NamedTemporaryFile
import configparser
import json
import os
import sys
import requests
import shutil
import ffmpeg
import pydub
from importlib import import_module


class TimeUtils:

    @staticmethod
    def time_string(ms):
        total_seconds = round(ms / 1000.0, 1)
        mins = int(total_seconds) // 60
        secs = total_seconds % 60
        return '{:02d}:{:04.1f}'.format(mins, secs)

    @staticmethod
    def interval_string(s, e, ifInvalid = 'n/a'):
        if (s >= e):
            return ifInvalid
        ss = TimeUtils.time_string(s)
        es = TimeUtils.time_string(e)
        return f'{ss} - {es}'


def lookup(selected_text, lookup_module_name):
    mod = import_module(lookup_module_name)
    lookup = getattr(mod, 'lookup')
    return lookup(selected_text)


def audiosegment_from_mp3_time_range(path_to_mp3, starttime_ms, endtime_ms):
    """Make an audio clip from mp3 _very quickly_ using ffmpeg-python."""
    # ref https://github.com/jiaaro/pydub/issues/135

    duration_ms = endtime_ms - starttime_ms
    seg = None
    with NamedTemporaryFile("w+b", suffix=".mp3") as f:
        ffmpeg_cmd = (
            ffmpeg
            .input(path_to_mp3, ss = (starttime_ms/1000.0), t = (duration_ms/1000.0))

            # vsync vfr added per https://stackoverflow.com/questions/18064604/
            #   frame-rate-very-high-for-a-muxer-not-efficiently-supporting-it
            # loglevel added to quiet down ffmpeg console output.
            .output(f.name, acodec='copy', **{'vsync':'vfr', 'loglevel':'error'})
            .overwrite_output()
        )
        # print('args:')
        # print(ffmpeg_cmd.get_args())
        ffmpeg_cmd.run()

        seg = pydub.AudioSegment.from_mp3(f.name)

    return seg


def anki_tag_from_filename(f):
    tag = os.path.basename(f)
    tag = ''.join([
        c
        for c in tag
        if c.isalnum() or c in "._- "
    ])
    if tag == '.mp3':
        tag = 'Unknown.mp3'
    tag = tag.replace(' ', '-')
    return tag


def anki_card_export(
        audiosegment,
        ankiconfig,
        transcription = None,
        tag = None):
    """Export the current clip and transcription to Anki using Ankiconnect."""

    now = datetime.now() # current date and time
    date_time = now.strftime("%Y%m%d_%H%M%S")
    filename = f'clip_{date_time}_{id(audiosegment)}.mp3'
    destdir = ankiconfig['MediaFolder']
    destname = os.path.join(destdir, filename)

    with NamedTemporaryFile(suffix='.mp3') as temp:
        audiosegment.export(temp.name, format="mp3")
        shutil.copyfile(temp.name, destname)
        # print('Generated temp clip:')
        # print(temp.name)
        # print('Copied clip to:')
        # print(destname)

    fields = {
        ankiconfig['AudioField']: f'[sound:{filename}]'
    }

    if transcription is not None and transcription != '':
        fields[ ankiconfig['TranscriptionField'] ] = transcription.strip().replace("\n", '<br>')

    postjson = {
        "action": "addNote",
        "version": 6,
        "params": {
            "note": {
                "deckName": ankiconfig['Deck'],
                "modelName": ankiconfig['NoteType'],
                "fields": fields
            }
        }
    }

    if tag is not None and tag != '':
        postjson['params']['note']['tags'] = [ tag ]

    print(f'posting: {postjson}')
    url = ankiconfig['Ankiconnect']
    r = requests.post(url, json = postjson)
    print(f'result: {r.json()}')

    e = r.json()['error']
    if e is not None:
        raise RuntimeError(e)

    return r
