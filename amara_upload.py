#!/usr/bin/env python3
from subprocess import Popen, PIPE
import argparse, sys, requests
from pprint import pprint
from api.amara_api import Amara
from utils import answer_me, download_yt_subtitles


# We suppose that the uploaded subtitles are complete (non-critical)
is_complete = True # do we upload complete subtitles?
sub_format = 'vtt'

def read_cmd():
   """Function for reading command line options."""
   desc = "Program for uploading subtitles to Amara. There are three modes of operation, depending on the source of the subtitles. \
           You can get the subtitles from YouTube, or upload subtitles files, or copy subtitles between Amara videos. \
           The format of the input file depends on the mode of operation (see 'sample_input.dat')"
#  parser = argparse.ArgumentParser(description=desc, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
   parser = argparse.ArgumentParser(description=desc)
   parser.add_argument('input_file',metavar='INPUT_FILE', help='Text file containing YouTube IDs and possibly filenames.')
   parser.add_argument('-l','--lang',dest='lang',required = True, help='Which language do we copy?')
   parser.add_argument('-f',dest='files', action="store_true",  help='Upload subtitles from files to Amara.')
   parser.add_argument('-y',dest='yt', action="store_true", help='Download subtitles from YouTube and upload them to Amara.')
   parser.add_argument('-a',dest='amara', action="store_true", help='Copy subtitles between two same Amara videos.')
   parser.add_argument('--skip-errors', dest='skip', default=False, action="store_true", help='Should I skip subtitles that could not be downloaded? \
         The list of failed YTID\' will be printed to \"failed_yt.dat\".')
   parser.add_argument('--rewrite', dest='always_rewrite', action="store_true", help='Always rewrite existing subtitles on upload. Use with extreme care')
   parser.add_argument('--no-rewrite', dest='never_rewrite', action="store_false", help='Never rewrite existing subtitles on upload.')
   return parser.parse_args()

opts = read_cmd()
infile = opts.input_file
lang = opts.lang
never_rewrite  = not opts.never_rewrite
always_rewrite = opts.always_rewrite

# We suppose that the original language is English
if lang == "en": 
    is_original = True # is lang the original language of the video?
else:
    is_original = False

if opts.yt == True and opts.files == True and opts.amara == True:
    print('Conflicting options "-f", "-y" and/or "-a"')
    print('Type "-h" for help')
    sys.exit(1)
    
if opts.yt == False and opts.files == False and opts.amara == False:
    print('Please, set either "-f", "-y" or "-a".')
    print('Type "-h" for help')
    sys.exit(1)


# List ytids may also contain filenames
ytids = []
# Reading file with YT id's
with open(infile, "r") as f:
    for line in f:
        l = line.split()
        if len(l) > 0 and l[0][0] != "#":
            ytids.append(line.split())

AMARA_USERNAME = 'dhbot'
amara = Amara(AMARA_USERNAME)

try:
    os.remove('youtubedl.out')
    os.remove('youtubedl.err')
except:
    pass

if len(ytids) < 20: # Do not print for large inputs
   print("This is what I got from the input file:")
   print(ytids)

# Main loop
for i in range(len(ytids)):
    ytid_from = ytids[i][0]

    if opts.amara == True:
        ytid_to = ytids[i][1]
    else:
        ytid_to = ytids[i][0]

    video_url_from = 'https://www.youtube.com/watch?v=%s' % ytid_from
    video_url_to = 'https://www.youtube.com/watch?v=%s' % ytid_to

#   PART 1: GETTING THE SUBTITLES 
    # set this to false if you want to download only
    # when language is missing on Amara
    download_first = False
    subs = False
    if opts.yt and download_first == True:
        subs = download_yt_subtitles(lang, sub_format, ytid_from)
        if not subs:
            if opts.skip:
                answer = True
            else:
                answer = answer_me("Should I continue with the rest anyway?")
            if answer:
                continue
            else:
                sys.exit(1)

    elif opts.files == True:
        f = open(ytids[i][1],"r")
        subs = f.read()

    elif opts.amara == True:
        # First, get first Amara ID
        amara_response = amara.check_video(video_url_from)
        if amara_response['meta']['total_count'] == 0:
            print("ERROR: Source video is not on Amara! YTID=%s" % ytid_from)
            sys.exit(1)
        else:
            amara_id_from =  amara_response['objects'][0]['id']
            amara_title =  amara_response['objects'][0]['title']
            print("Copying "+lang+" subtitles from YTID=", ytid_from)
            print("Title: "+amara_title)
            print(amara.AMARA_BASE_URL + lang + '/videos/' + amara_id_from)

        # Check whether subtitles for a given language are present,
        is_present, sub_version = amara.check_language(amara_id_from, lang)
        if is_present:
            print("Subtitle revision number: %d" % sub_version)
        else:
            print("ERROR: Amara does not have subtitles in "+lang+" language for this video!")
            sys.exit(1)
 
        # Download subtitles from Amara for a given language
        subs = amara.download_subs(amara_id_from, lang, sub_format)


#   PART 2: UPLOADING THE SUBTITLES 

    # Now check whether the video is already on Amara
    # If not, create it.
    amara_response = amara.check_video(video_url_to)
    if amara_response['meta']['total_count'] == 0:
        amara_response = amara.add_video(video_url_to, lang)
        amara_id = amara_response['id']
        amara_title =  amara_response['title']
        print("Created video on Amara with Amara id %s" % amara_id)
        print("Title: " + amara_title)
        print(amara.AMARA_BASE_URL + lang + '/videos/' + amara_id)
    else:
        amara_id =  amara_response['objects'][0]['id']
        amara_title =  amara_response['objects'][0]['title']
        print("Video with YTid " + ytid_to + " is already present on Amara")
        print("Title: " + amara_title)
        print(amara.AMARA_BASE_URL + lang + '/videos/' + amara_id)

    # When copying between 2 Amara videos, make sure that they have the same length
    # If not, ask the user whether to proceed anyway (might screw up the subs timing)

    if opts.amara == True:
        amara.compare_videos(amara_id_from, amara_id)

    # First check, whether subtitles for a given language are present,
    # then upload subtitles
    is_present, sub_version = amara.check_language(amara_id, lang)
    if is_present and sub_version != 0:
        print("Language %s is already present in Amara video id:%s" % (opts.lang, amara_id))
        print("Subtitle revision number: %d" % sub_version)
        if never_rewrite:
           answer = False
        elif always_rewrite:
           answer = True
        else:
           answer = answer_me("Should I upload the subtitles anyway?")
        if not answer:
            continue
    else:
        r = amara.add_language(amara_id, lang, is_original)

    # In certain cases we may want to download here
    if not subs:
        subs = download_yt_subtitles(lang, sub_format, ytid_from)
        if not subs:
            if opts.skip:
                answer = True
            else:
                answer = answer_me("Should I continue with the rest anyway?")
            if answer:
                continue
            else:
                sys.exit(1)

    r = amara.upload_subs(amara_id, lang, is_complete, subs, sub_format)
    if r['version_number'] == sub_version + 1:
        print('Succesfully uploaded subtitles to: '+r['site_uri'])
    else:
        print("This is weird. Something probably went wrong during upload.")
        print("This is the response I got from Amara")
        pprint(r)
        sys.exit(1)

    print('----------------------------------------')

