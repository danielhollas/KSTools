#!/usr/bin/env python3
from subprocess import Popen, PIPE, call, check_call
import argparse, sys
from pprint import pprint
from amara_api import *
from utils import eprint, epprint
import os


# We suppose that the uploaded subtitles are complete (non-critical)
is_complete = True # do we upload complete subtitles?

# DH TODO automatically handle missing YT sub formats
# converting to srt can be done via
# ffmpeg -i foo.vtt foo.srt
# currently youtube-dl convert does not work when not downloading the video
sub_format = 'vtt'
sub_format2 = "srt"

def read_cmd():
   """Function for reading command line options."""
   desc = "Program for syncing subtitles from YouTube to Amara. \
           Aimed for large numbers, should be faster then script amara_upload."
   parser = argparse.ArgumentParser(description=desc)
   parser.add_argument('input_file',metavar='INPUT_FILE', help='Text file containing YouTube IDs in the first column.')
   parser.add_argument('-l','--lang',dest='lang',default = "en", help='Which language do we copy?')
   parser.add_argument('-c','--credentials',dest='apifile',default='myapi.txt', help='Text file containing your API key and username on the first line.')
   parser.add_argument('-v','--verbose',dest='verbose',default=False,action="store_true", help='More verbose output.')
   parser.add_argument('--skip-errors', dest='skip', default=True, action="store_true", help='[default]Should I skip subtitles that could not be downloaded? \
         The list of failed YTID\' will be printed to \"failed_yt.dat\".')
   parser.add_argument('--no-rewrite', dest='rewrite', default=False, action="store_false", help='[default]Never rewrite existing subtitles on upload!')
   return parser.parse_args()

opts = read_cmd()
infile = opts.input_file
apifile = opts.apifile
lang = opts.lang

# We suppose that the original language is English
if lang == "en": 
    is_original = True # is lang the original language of the video?
else:
    is_original = False

print("# Syncing subtitles for language:", lang)

ytids = []
# Reading file with YT id's
with open(infile, "r") as f:
    for line in f:
        ytids.append(line.split())

# File 'apifile' should contain only one line with your Amara API key and Amara username.
# Amara API can be found in Settins->Account-> API Access (bottom-right corner)
file = open(apifile, "r")
API_KEY, USERNAME = file.read().split()[0:]
print('# Using Amara username: '+USERNAME)
#print('Using Amara API key: '+API_KEY)

call("rm -f youtubedl.err youtubedl.out failed_yt.dat", shell=True)

amara_headers = {
   'Content-Type': 'application/json',
   'X-api-username': USERNAME,
   'X-api-key': API_KEY,
   'format': 'json'
}

# Read file with existing videos, will be easier to then checking via Internet
# Append every updated video
try:
    os.mkdir("subs")
except:
    pass

f_vids = open("videos_on_amara."+lang+".dat", "a+")
f_vids.seek(0)
# Using set instead of list for faster search
ytid_exist = set()
for l in f_vids:
    ytid_exist.add(l.split()[0])


# Skip certain videos
ytid_skip = set()
try:
    with open("skip_videos.dat","r") as f:
        for l in f:
            ytid_skip.add(l)
except:
    pass

# Main loop
for i in range(len(ytids)):
    video_present = False
    lang_present  = False
    lang_visible  = False
    ytid_from = ytids[i][0]

    video_url_from = 'https://www.youtube.com/watch?v='+ytid_from
    video_url_to = 'https://www.youtube.com/watch?v='+ytid_from

#   PART 1: Checking the existence of subtitles on Amara
#   If present, we do nothing
    if ytid_from in ytid_exist or ytid_from in ytid_skip:
        continue

    sys.stdout.flush()
    sys.stderr.flush()
    f_vids.flush()

#   Check whether video is there
    amara_response = check_video( video_url_to, amara_headers)
    if amara_response['meta']['total_count'] == 0:
        video_present = False
        lang_present  = False
    else:
        video_present = True
        amara_id = amara_response['objects'][0]['id']
        amara_title = amara_response['objects'][0]['title']
        # We don't really need check_language() here
        # This also avoids some API errors
        for lg in amara_response['objects'][0]['languages']:
            if lg["code"] == lang:
                lang_present = True
                # lang could be there, but with no revisions
                if lg["visible"] == True:
                    lang_visible = True
                break
#       lang_present, sub_version = check_language(amara_id, lang, amara_headers)
        if lang_present and lang_visible:
            f_vids.write(ytid_from+'\n')
            if opts.verbose:
                print("Subtitles already present for video YTID: ", ytid_from )    
            continue

    # Moved this here due to large number of Amara errors...
    if not video_present:
        amara_response = add_video(video_url_to, lang, amara_headers)
        if "id" in amara_response:
            amara_id = amara_response['id']
            amara_title =  amara_response['title']
        else:
            print("ERROR: During adding video to Amara:", ytid_from)
            continue
        if opts.verbose:
            print("Created video on Amara with Amara id "+amara_id)
            print(AMARA_BASE_URL+'cs/videos/'+amara_id)


#   PART 2: GETTING THE SUBTITLES 
    # If we don't aim to overwrite the subtitles, skipped downloading them in the first place
    ytdownload = 'youtube-dl --sub-lang '+lang+ \
    ' --sub-format '+sub_format+' --write-sub --skip-download '+ video_url_from
    
    p = Popen(ytdownload, shell=True, stdout=PIPE, stderr=PIPE)
    out, err = p.communicate()
    with open("youtubedl.out", "a") as f:
        f.write(out.decode('UTF-8'))
    if err:
        with open("youtubedl.err", "a") as f:
            f.write(err.decode('UTF-8'))
        print("ERROR: during downloading subs:", ytid_from)
        continue

    fname = out.decode('UTF-8').split('Writing video subtitles to: ')
    if len(fname) < 2:
       print("ERROR: Requested subtitles were not found on YouTube. ", ytid_from)
       with open("failed_yt.dat","a") as f:
           f.write(ytid_from+'\n')
       continue


    fname = fname[1].strip('\n')
    with open(fname, 'r') as content_file:
       subs = content_file.read()

    os.rename(fname,"subs/"+fname)

#   PART 3: Creating language on Amara

    if not lang_present:
        r = add_language(amara_id, lang, is_original, amara_headers)

#   PART 4: UPLOADING THE SUBTITLES 
    r = upload_subs(amara_id, lang, is_complete, subs, sub_format, amara_headers)
    if not 'version_no' in r:
        print('ERROR: when uploading subs to Amara:',ytid_from)
        epprint(ytid_from)
        epprint(r)
        continue
    # this is not possible here, we dont have sub_version
#    if r['version_no'] == sub_version+1:
    else:
        print('Succesfully uploaded subtitles: ',ytid_from)
        f_vids.write(ytid_from+'\n')

