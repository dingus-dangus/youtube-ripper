from subprocess import Popen, PIPE
from os import stat, path, remove
from pytube import YouTube
from time import sleep
from re import sub
VALID_AV_TYPES = ['mp4', 'webm']


def decide():
    """Get user input if no argument was passed"""
    links = []
    if not path.isfile('ffmpeg.exe'):
        print('ffmpeg is missing! Need ffmpeg in the same folder to work')
        sleep(5)
        exit()
    if path.isfile('input.txt'):
        print('Using input.txt for a list of YouTube links...')
        with open('input.txt') as f:
            for line in f.read().splitlines():
                links.append(line.rstrip())
    else:
        links.append(input('YouTube Link: '))
    return links


def get_best_streams(yt):
    """Returns highest bitrate valid streams,
    returns None for audio if only progressive videos were found"""
    streams = yt.streams.filter(adaptive=True).order_by('bitrate').asc().all()
    best_audio, best_video, title = None, None, None
    for stream in streams:
        if stream.mime_type.split('/')[0] == 'audio' and stream.mime_type.split('/')[1] in VALID_AV_TYPES:
            best_audio = stream
            audio_ext = stream.mime_type.split('/')[1]
        if stream.mime_type.split('/')[0] == 'video' and stream.mime_type.split('/')[1] in VALID_AV_TYPES:
            best_video = stream
            video_ext = stream.mime_type.split('/')[1]
    if not best_video or not best_audio:
        best_video = yt.streams.filter(progressive=True).order_by('bitrate').desc().first()
        video_ext = stream.mime_type.split('/')[1]
    q_str = 'normal' if not best_audio else 'high'
    yt_title = yt.title
    yt_fps = best_video.fps
    print('Found %s quality stream for:\n' % q_str + yt_title)
    return best_video, video_ext, best_audio, audio_ext, yt_title, yt_fps


def progress_bar(length=25,progress=0):
    """Return a nice progress bar"""
    bar = '['
    if progress <= 0:  # prevent div by 0
        for seg in range(length):
            bar += ' '
        bar += ']'
        return bar
    done_segs = int(progress / (100 / length) - 1)
    blank_segs = length - done_segs - 1
    for seg in range(done_segs):
        bar += '-'
    bar += '>'
    for seg in range(blank_segs):
        bar += ' '
    bar += ']'
    if progress == 100:
        bar += '\n'
    return bar


def return_progress(stream=None, chunk=None, file_handle=None, bytes_remaining=None):
    """Called upon to update the progress meter"""
    percentage = (1 - bytes_remaining / stream.filesize) * 100
    bar_str = progress_bar(progress=percentage)
    print(bar_str + '\r', end='')


def cleanup(stripped_filename, youtube_title, video_ext='mp4', audio_ext='mp4', mux_failure=False):
    print("Cleaning up")
    if path.isfile(stripped_filename + '.' + video_ext):
        remove(stripped_filename + '.' + video_ext)
    if path.isfile('unmuxed-video-' + stripped_filename + '.' + video_ext):
        remove('unmuxed-video-' + stripped_filename + '.' + video_ext)
    if path.isfile('unmuxed-audio-' + stripped_filename + '.' + audio_ext):
        remove('unmuxed-audio-' + stripped_filename + '.' + audio_ext)
    if mux_failure:
        if path.isfile(youtube_title + '.' + 'mp4'):
            remove(youtube_title + '.' + 'mp4')


if __name__ == '__main__':
    input_list = decide()
    for link in input_list:
        yt, skip_download = None, False
        try:
            yt = YouTube(link)
            yt.register_on_progress_callback(return_progress)
        except BaseException as e:
            if e == 's':
                print('PyTube library error, this is not my fault!!! REEEEEEE')
            else:
                print('Fatal error: ' + str(e))
        if yt:
            try:
                best_video_result, v_ext, best_audio_result, a_ext, title, fps = get_best_streams(yt)
                filename = sub(r'\W+', '', title.strip(' ').lower()[:10])
                if not best_audio_result:
                    #  Low quality streams only, no muxing required
                    video_size = best_video_result.filesize
                    if path.isfile(filename + '.' + v_ext):
                        print('File already exists!')
                        if stat(filename + '.' + v_ext).st_size == video_size:
                            print('And it is the same filesize as the stream\nSkipping download')
                            skip_download = True
                        else:
                            print('But our copy is', stat(filename + '.' + v_ext).st_size / 1024,
                                  'while the stream is', video_size / 1024, 'kB')
                    if not skip_download:
                        print('Downloading video (%sMB)' % "{0:.2f}".format(video_size / 1000000))
                        best_video_result.download(filename=filename)
                else:
                    #  High quality stream found, muxing required
                    video_size = best_video_result.filesize
                    audio_size = best_audio_result.filesize
                    est_muxed_filesize = video_size + audio_size
                    if path.isfile(title + '.' + 'mp4'):
                        print('File might already exist!')
                        size_diff = stat(title + '.' + 'mp4').st_size / est_muxed_filesize
                        if 1.1 >= size_diff >= 0.9:
                            print('and it is roughly same filesize as the stream\nSkipping download')
                            skip_download = True
                        else:
                            print('But our copy is', stat(title + '.' + 'mp4').st_size / 1024, 'kB',
                                  'while the stream is', video_size / 1024 + audio_size / 1024, 'kB')
                    if not skip_download:
                        print('Downloading video (%sMB)' % "{0:.2f}".format(video_size / 1000000))
                        best_video_result.download(filename='unmuxed-video-' + filename)
                        print('Downloading audio (%sMB)' % "{0:.2f}".format(audio_size / 1000000))
                        best_audio_result.download(filename='unmuxed-audio-' + filename)
            except BaseException as e:
                if len(input_list) == 1:
                    error_msg = 'No streams found or downloading error:\n' + str(e)
                else:
                    error_msg = 'No streams found or downloading error for video\n'\
                                + str(input_list.index(link) + 1) + ' in list.\n(%s)\n%s' % (link, str(e))
                print(error_msg)

        #  if muxing needs to be done for this video
        if best_audio_result and not skip_download:
            cmd = 'ffmpeg -y -i %s -r %s -i %s "%s.mp4"' % (
                'unmuxed-audio-' + filename + '.' + a_ext, str(fps),
                'unmuxed-video-' + filename + '.' + v_ext, title)
            try:
                enc = Popen(cmd, stdout=PIPE)
                enc.communicate()
                if enc.returncode != 0:
                    print('Something went wrong muxing!')
                    cleanup(filename, title, video_ext=v_ext, audio_ext=a_ext, mux_failure=True)
                else:
                    print('Muxing successful! Output is:\n' + title + '.mp4')
                    cleanup(filename, title, video_ext=v_ext, audio_ext=a_ext)
            except BaseException as e:
                print(str(e))
    print("Press the 'any' key to exit")
    input()

