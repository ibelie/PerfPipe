# -*- coding: utf-8 -*-
# Copyright 2017 - 2020 ibelie, Chen Jie, Joungtao. All rights reserved.
# Use of this source code is governed by The MIT License
# that can be found in the LICENSE file.

from __future__ import print_function

import os
import codecs
import config
import process
from ruamel import yaml
from properform import memory_leak
from properform import properform

def run(user, project, tag, commit):
	dirpath = os.path.join(config.PROFILE_PATH, user, project, tag, commit)
	counter = yield os.path.join(dirpath, 'profile.lock')

	infopath = os.path.join(config.PROFILE_PATH, user, project, tag, commit, 'statistics.yml')
	if os.path.isfile(infopath):
		with codecs.open(infopath, 'r', 'utf-8') as f:
			commitinfo = yaml.load(f, Loader = yaml.RoundTripLoader) or {}
	else:
		commitinfo = {}

	while counter is not None:
		last_time = 0
		fileset = set()
		funcset = set()
		for i in range(config.MAX_COUNT):
			filepath = os.path.join(dirpath, '%d.prof' % i)
			if not os.path.isfile(filepath): continue

			mtime = os.stat(filepath).st_mtime
			if mtime > last_time: last_time = mtime

			with open(filepath, 'rb') as f:
				for t, data in properform.Iterate(f):
					if t == properform.DATA_TYPE_PROFILE:
						for (f, l, n), (pc, rc, it, ct, callers) in data.items():
							fileset.add(f)
							funcset.add(n)
							for (f, l, n), (pc, rc, it, ct) in callers.items():
								fileset.add(f)
								funcset.add(n)

		if commitinfo.get('last_time', 0) < last_time:
			commitinfo['last_time'] = last_time
			commitinfo['file_count'] = len(fileset)
			commitinfo['func_count'] = len(funcset)

			with codecs.open(infopath, 'w', 'utf-8') as f:
				yaml.dump(commitinfo, f, Dumper = yaml.RoundTripDumper)

			with process.MutexData(os.path.join(config.PROFILE_PATH, user, project, tag, 'info.yml')) as d:
				if not d.last_time or d.last_time < last_time:
					d.last_time = last_time
					d.last_commit = commit

			counter = yield True
		else:
			counter = yield False
