#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Actions:

  For each playlist,

  1 - Download the playlist entries from a playlist url.

  2 - Download the files from that playlist in m4a format.
      Filenames will have the youtube id as a suffix.

  3 - Update m4a attributes to match artist, title, track number,
      genre.

  Note:

    Track numbers are obtained from a song's first occurrence in a
    playlist, if there are multiple occurrences.

    Running the script again on the same playlist will reannotate
    the track numbers.
"""

import sys
import os
import os.path
import subprocess
import re
import glob
import json
import tempfile
import shutil

class Playlist(object):
	__slots__ = ["name", "genre", "url", "entries"]

	def __init__(self, name, genre, url):
		self.name = name
		self.genre = genre
		self.url = url
		self.entries = {}

	def __len__(self):
		return len(self.entries)

	def get_entry(self, entry_id):
		return self.entries.get(entry_id, None)

	def populate(self, entries):
		"""provides the list of entries of the list. Allows track positions to be recovered based on id.

           {"url": "dYGgqJiJZCA", "_type": "url", "ie_key": "Youtube", "id": "dYGgqJiJZCA", "title": "Moe Turk - Together (Anton Ishutin Remix)"}

		The entries are given in playlist order. All entries in the playlist must be given at once.
		"""
		for i, entry in enumerate(entries):
			entry["pos"] = i + 1
			self.entries[entry["id"]] = entry

DEFAULT_ROOT = "/MIRROR/mp3/youtube/"

PLAYLISTS = (
	Playlist("House Deep and Shallow",
			 "Deep House",
			 "https://www.youtube.com/playlist?list=PLE6Dqzv8ViTSB3Bb2yO2bSUsLnKYJWQ-H"),
)

DL_ARGS = [
	"youtube-dl",
	"--download-archive", "youtube-dl.archive",
	"--extract-audio",
	"--audio-format", "m4a",
	"--embed-thumbnail",
	"--prefer-ffmpeg"]

# Downloads a playlist listing.
DL_LIST_ARGS = [
	"youtube-dl",
	"--flat-playlist",
	"--yes-playlist",
	"-j"
]

def ensure_dir(d):
	if not os.path.exists(d):
		os.makedirs(d)

def m4a_atoms(fname):
	cmd = ["AtomicParsley",
		   fname,
		   "-t"]
	popen = subprocess.Popen(cmd,
							 stdout=subprocess.PIPE, stderr=sys.stderr)
	stdout, stderr = popen.communicate()
	if popen.returncode != 0:
		print >> sys.stderr, "AP cmd %s failed with code: %s" % (cmd, popen.returncode)
		raise Exception("AtomicParsley failed")
	atoms = stdout.splitlines()

	def parse_line(l):
		#Atom "©too" contains: Lavf57.24.101
		toks = l.split(" ", 3)
		return toks[1][1:-1], toks[3]

	a_dict = { p[0]: p[1] for p in [parse_line(l) for l in atoms] }
	trackno = a_dict.get("trkn", "")
	if trackno:
		# AtomicParsley prints track numbers as "X of Y"
		# but they are set with "X/Y" syntax
		nums = trackno.split(" of ", 1)
		if len(nums) > 1:
			a_dict["trkn"] = "%s/%s" % nums

	return a_dict

def split_artist(s):
	"""returns (artist, title) from a long " X - Foo " description"""
	try_split = s.split(" - ", 1)
	if len(try_split) > 1:
		return [x.strip() for x in try_split]
	try_split = s.split("-", 1)
	if len(try_split):
		return [x.strip() for x in try_split]
	
	print >> sys.stderr, "Warning: could not split name %s." % (s,)
	return (None, s)

def update_m4a_meta(pl, meta, m4a):
	trackno = "%d/%d" % (meta["pos"], len(pl))
	current_atoms = m4a_atoms(m4a)
	title = meta["title"]
	artist, song = split_artist(title)

	update_command = []
	#"trkn"        tracknum
	#'\xc2\xa9nam' title
	#'\xc2\xa9ART' artist
	#'\xc2\xa9gen' genre
	if '\xc2\xa9nam' not in current_atoms and song is not None:
		update_command += ["--title", song]
	if '\xc2\xa9ART' not in current_atoms and artist is not None:
		update_command += ["--artist", artist]

	# we can update the track number if it changes
	if trackno !=  current_atoms.get("trkn", ""):
		update_command += ["--tracknum", str(trackno)]

	if not '\xc2\xa9gen' in current_atoms and pl.genre is not None:
		update_command += ["--genre", pl.genre]

	if update_command:
		# one or more attributes needs changing
		fd, temp_name = tempfile.mkstemp(suffix="playlist-dl")
		os.close(fd)
		cmd = ["AtomicParsley", m4a,
			   "--output", temp_name
		   ] + update_command
		popen = subprocess.Popen(cmd,
								 stdout=sys.stdout, stderr=sys.stderr)
		popen.communicate()
		if popen.returncode != 0:
			print >> sys.stderr, "AP cmd %s failed with code: %s" % (cmd, popen.returncode)
			raise Exception("AtomicParsley failed")
		shutil.move(temp_name, m4a)

		print >> sys.stdout, "Attributes for %s updated: %s" % (m4a, update_command)
	else:
		print >> sys.stdout, "Attributes for %s already present. Skipping." % (m4a,)


def do_track_meta(pl):
	"""changes the track metadata for every song in the list"""

	dirpath = os.path.join(DEFAULT_ROOT, pl.name)
	ensure_dir(dirpath)
	m4as = glob.glob(os.path.join(dirpath, "*.m4a"))
	for m4a in m4as:
		# assumes ID is at the end of the filename
		toks = re.split("-([-a-zA-Z0-9_]{11})[.]m4a$", m4a)
		entry_id = toks[-2]
		entry = pl.get_entry(entry_id)
		if not entry:
			print >> sys.stderr, "File %s not part of playlist. Skipping." % (m4a,)
			continue

		update_m4a_meta(pl, entry, m4a)

def do_dl_listing(pl):
	dirpath = os.path.join(DEFAULT_ROOT, pl.name)
	ensure_dir(dirpath)

	attempt = 0
	def _listing_file(num):
		return os.path.join(dirpath, "listing.%03d.txt" % (attempt,))

	while os.path.exists(_listing_file(attempt)):
		attempt += 1
		if attempt > 999:
			raise Exception("Ran out of names.")

	fd = -1
	fo = None
	try:
		print >> sys.stdout, "Writing playlist listing to %s." % (_listing_file(attempt),)

		# racey
		fd = os.open(_listing_file(attempt), os.O_RDWR | os.O_CREAT | os.O_EXCL)

		fo = os.fdopen(fd, "w+")
		
		cmd = DL_LIST_ARGS + [pl.url]
		popen = subprocess.Popen(cmd,
								 stdout=subprocess.PIPE, stderr=sys.stderr,
								 cwd=dirpath)
		stdout, stderr = popen.communicate()
		if popen.returncode != 0:
			print >> sys.stderr, "youtube-dl failed with code:", popen.returncode
			raise Exception("youtube-dl failed")

		entries = [json.loads(x) for x in stdout.splitlines()]
		pl.populate(entries)
		fo.write(stdout)
	finally:
		if fo is not None:
			fo.close()
		elif fd > -1:
			os.close(fd)

def do_dl_media(pl):
	dirpath = os.path.join(DEFAULT_ROOT, pl.name)
	ensure_dir(dirpath)

	cmd = DL_ARGS + [pl.url]
	popen = subprocess.Popen(cmd,
							 stdout=sys.stdout, stderr=sys.stderr,
							 cwd=dirpath)
	popen.communicate()
	if popen.returncode != 0:
		print >> sys.stderr, "youtube-dl %s failed with code: %s" % (cmd, popen.returncode)
		raise Exception("youtube-dl failed")

def main():
	for pl in PLAYLISTS:
		do_dl_listing(pl)
		#do_dl_media(pl)
		do_track_meta(pl)

if __name__ == "__main__":
	main()
