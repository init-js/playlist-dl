# youtube-dl
Manage Offline Versions of Youtube Playlists

A quick and dirty script to take a list of playlists offline. It is
based on youtube-dl (for ffmpeg, as I've not had success with the
default youtube+avconv combo), and AtomicParsley to get the artwork
and song/album metadata inside the m4as.

It downloads the contents of a youtube playlist to a directory, uses
the youtube thumbnail as cover art, and splits the title of the
youtube video into Artist - Song.

The name of the playlist is inscribed inside the Album for each entry,
so that they may be grouped together in the music player.

