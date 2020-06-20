#-*- coding: utf-8 -*-
# Copyright 2019 ibelie, Chen Jie, Joungtao. All rights reserved.
# Use of this source code is governed by The MIT License
# that can be found in the LICENSE file.

from app import route, response
from process import Runner
from ruamel import yaml
import config
import codecs
import os

BADPATH = '../', '/..'
TOKEN = ''

TASK_RETRY = 3
TASK_INTERVAL = 5

def _check(info, project, commit):
	commitpath = os.path.join(config.COMMIT_INFO, info['user'], project, '%s.yml' % commit)
	if os.path.isfile(commitpath):
		with codecs.open(commitpath, 'r', 'utf-8') as f:
			commitinfo = yaml.load(f, Loader = yaml.RoundTripLoader)
			return ''
	else:
		commitinfo = None
		commitdir = os.path.dirname(commitpath)
		if not os.path.isdir(commitdir): os.makedirs(commitdir)

		if info['type'] == 'github':
			request = Request('https://api.github.com/repos/%(user)s/%(project)s/git/commits/%(commit)s?access_token=%(token)s' % {
				'user': info['user'],
				'project': project,
				'commit': commit,
				'token': TOKEN,
			})
			response = json.loads(urlopen(request).read())
			if response.get('sha') == commit:
				commitinfo = response

		if commitinfo:
			with codecs.open(commitpath, 'w', 'utf-8') as f:
				yaml.dump(commitinfo, f, Dumper = yaml.RoundTripDumper)
				return ''

	return 'Commit (%s) Error!' % commit

@route(useSubmit = True)
def profile(submit, token, project, commit, tag):
	for badpath in BADPATH:
		if badpath in token or badpath in project or badpath in commit:
			return 'System Error!'

	info = None
	infopath = os.path.join(config.USER_INFO, '%s.yml' % token)
	if os.path.isfile(infopath):
		with codecs.open(infopath, 'r', 'utf-8') as f:
			info = yaml.load(f, Loader = yaml.RoundTripLoader)
	if not info: return 'Token (%s) Error!' % token

	error = _check(info, project, commit)
	if not error:
		dirpath = os.path.join(config.PROFILE_PATH, info['user'], project, tag, commit)
		if not os.path.isdir(dirpath): os.makedirs(dirpath)
		for i in range(config.MAX_COUNT):
			filepath = os.path.join(dirpath, '%d.prof' % i)
			if not os.path.isfile(filepath):
				with open(filepath, 'wb') as f:
					for chunk in submit:
						f.write(chunk)
				Runner.profile(TASK_RETRY, TASK_INTERVAL, info['user'], project, tag, commit)
				break

	return response(error = error)
