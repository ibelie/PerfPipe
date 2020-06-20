# -*- coding: utf-8 -*-
# Copyright 2017 - 2020 ibelie, Chen Jie, Joungtao. All rights reserved.
# Use of this source code is governed by The MIT License
# that can be found in the LICENSE file.

from __future__ import print_function

import os
import gc
import imp
import sys
import uuid
import time
import codecs
import config
import weakref
import tempfile
import traceback
from ruamel import yaml

PROCESSOR_PATH = os.path.dirname(os.path.realpath(__file__))

if sys.platform == 'win32':
	PROCESS = os.path.normpath(os.path.join(PROCESSOR_PATH, 'process.bat'))

	def lock(file): pass
	def unlock(file): pass

	def openlog(name): pass
	def log(text): print(text)

else:
	PROCESS = os.path.normpath(os.path.join(PROCESSOR_PATH, 'process.sh'))

	import fcntl
	def lock(file):
		fcntl.flock(file.fileno(), fcntl.LOCK_EX)
	def unlock(file):
		fcntl.flock(file.fileno(), fcntl.LOCK_UN)

	import syslog
	def openlog(name): syslog.openlog('Processor[%s]' % name, syslog.LOG_PID)
	def log(text): syslog.syslog(str(text))

class MutexData(object):
	def __init__(self, mutexfile):
		if not os.path.isfile(mutexfile):
			if not os.path.isdir(os.path.dirname(mutexfile)):
				os.makedirs(os.path.dirname(mutexfile))
			with open(mutexfile, 'wb') as f: pass
		self.file = codecs.open(mutexfile, 'r+', 'utf-8')
		lock(self.file)
		self.data = yaml.load(self.file, Loader = yaml.RoundTripLoader) or {}

	def __getattr__(self, key, value = None):
		return self.data.get(key, value)

	def __setattr__(self, key, value):
		if key in ('file', 'data'):
			return object.__setattr__(self, key, value)
		self.data[key] = value

	def __delattr__(self, key):
		del self.data[key]

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_value, traceback):
		self.close()

	def close(self):
		if self.file is None: return
		self.file.seek(0)
		yaml.dump(self.data, self.file, Dumper = yaml.RoundTripDumper)
		self.file.truncate()
		unlock(self.file)
		self.file.close()
		self.file = None

class DuplicatedException(BaseException):
	pass

class Singleton(object):
	def __init__(self, lockfile = '', flavor_id = ''):
		self._initialized = False
		if lockfile:
			basename = lockfile
			self.lockfile = lockfile
		else:
			basename = os.path.splitext(os.path.abspath(sys.argv[0]))[0]
			basename = basename.replace('/', '-').replace(':', '').replace('\\', '-')
			if flavor_id:
				basename += '-%s' % flavor_id + '.lock'
			else:
				basename += '.lock'
			self.lockfile = os.path.normpath(tempfile.gettempdir() + '/' + basename)

		if sys.platform == 'win32':
			try:
				# file already exists, we try to remove (in case previous execution was interrupted)
				if os.path.exists(self.lockfile):
					os.unlink(self.lockfile)
				self.fd = os.open(self.lockfile, os.O_CREAT | os.O_EXCL | os.O_RDWR)
			except OSError:
				type, e, tb = sys.exc_info()
				if e.errno == 13:
					self.error = 'Another instance is already running, quitting.'
					raise DuplicatedException()
				log(e.errno)
				raise
		else:  # non Windows
			self.fp = open(self.lockfile, 'w')
			self.fp.flush()
			try:
				fcntl.lockf(self.fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
			except IOError:
				self.error = 'Another instance is already running, quitting.'
				raise DuplicatedException()

		self._initialized = True

	def __del__(self):
		if not self._initialized:
			return
		if sys.platform == 'win32':
			if hasattr(self, 'fd'):
				os.close(self.fd)
				os.unlink(self.lockfile)
		else:
			fcntl.lockf(self.fp, fcntl.LOCK_UN)
			# os.close(self.fp)
			if os.path.isfile(self.lockfile):
				os.unlink(self.lockfile)

class LogPrinter(object):
	def __init__(self, path):
		self.file = codecs.open(path, 'wb', 'utf-8')
		self.stdout = sys.stdout
		self.stderr = sys.stderr
		sys.stdout = sys.stderr = self

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_value, traceback):
		sys.stdout = self.stdout
		sys.stderr = self.stderr
		self.file.close()

	def write(self, stream):
		self.file.write(stream)
		self.file.flush()

class RunnerType(object):
	def __getattr__(self, task, value = None):
		def _run(retry, interval, *args):
			assert len(args) <= 6, 'Too many arguments!'
			run_command('%(process)s Runner_%(task)s %(retry)s %(interval)s %(args)s' % {
				'process': PROCESS,
				'task': task,
				'retry': retry,
				'interval': interval,
				'args': ' '.join(map(str, args)),
			})
		return _run

Runner = RunnerType()

class WorkerJobException(BaseException):
	pass

class WorkerCaller(object):
	def __init__(self, runner, name):
		self.runner = weakref.proxy(runner)
		self.name = name
		self.retry = 10000
		self.interval = 0.01

	def send(self, *args, **kwargs):
		return self.runner.send(self.name, *args, **kwargs)

	def __call__(self, worker, *args, **kwargs):
		return self.runner.call(worker, self.retry, self.interval, self.name, *args, **kwargs)

class WorkerRunner(object):
	def __init__(self, task):
		self.task = task

	def __call__(self, name, interval, *args):
		assert len(args) <= 6, 'Too many arguments!'
		run_command('%(process)s Worker_%(task)s %(name)s %(interval)s %(args)s' % {
			'process': PROCESS,
			'task': self.task,
			'name': name,
			'interval': interval,
			'args': ' '.join(map(str, args)),
		})

	def __getattr__(self, name, value = None):
		caller = WorkerCaller(self, name)
		setattr(self, name, caller)
		return caller

	@classmethod
	def get_lock_file(cls, task, worker):
		return os.path.join(PROCESSOR_PATH, 'worker', task, worker + '.lock')

	@classmethod
	def get_job_file(cls, task, worker):
		return os.path.join(PROCESSOR_PATH, 'worker', task, worker + '.yml')

	def send(self, worker, *args, **kwargs):
		job_file = self.get_job_file(self.task, worker)
		with MutexData(job_file) as d:
			job = args + (kwargs, )
			if not d.queue:
				d.queue = [job]
			elif job not in d.queue:
				d.queue.append(job)

	def call(self, worker, retry, interval, *args, **kwargs):
		job_uuid = str(uuid.uuid1())
		job_file = self.get_job_file(self.task, worker)
		while retry > 0:
			with MutexData(job_file) as d:
				if not d.queue and (not d.uuid or d.uuid == job_uuid):
					d.uuid = job_uuid
					d.job = args + (kwargs, )
					if d.result:
						del d.result
					break
			time.sleep(interval)
			retry -= 1

		while retry > 0:
			with MutexData(job_file) as d:
				if d.uuid != job_uuid:
					raise WorkerJobException()
				if d.result:
					del d.uuid
					return d.result
			time.sleep(interval)
			retry -= 1

class WorkerType(object):
	def __getattr__(self, task, value = None):
		worker = WorkerRunner(task)
		setattr(self, task, worker)
		return worker

Worker = WorkerType()

PROCESSORS = {}

def runner(task):
	retry, interval = sys.argv[2:4]
	try:
		generator = PROCESSORS[task].run(*sys.argv[4:])
		lock_file = next(generator)
	except Exception as e:
		log(traceback.format_exc())
		log(str(e))
		return

	singleton = Singleton(lock_file)

	log_prefix = '[retry=%(retry)s interval=%(interval)s args=%(args)s]' % {
		'retry': retry,
		'interval': interval,
		'args': repr(tuple(sys.argv[4:])),
	}
	log(log_prefix + 'Task Start')

	try:
		retry = int(retry)
		interval = float(interval)
		counter = 0
		retry_count = 0
		while True:
			counter += 1
			log(log_prefix + 'Task Counter %d (Retry %d)' % (counter, retry_count))
			result = generator.send(counter)
			gc.set_debug(0)
			gc.collect()
			if result:
				retry_count = 0
			else:
				retry_count += 1
				if retry_count >= retry: break
			time.sleep(interval)
		for _ in generator: pass
	except Exception as e:
		log(log_prefix + traceback.format_exc())
		log(log_prefix + str(e))

	log(log_prefix + 'Task End')

def worker(task):
	name, interval = sys.argv[2:4]
	try:
		generator = PROCESSORS[task].run(name, *sys.argv[4:])
		next(generator)
	except Exception as e:
		log(traceback.format_exc())
		log(str(e))
		return

	singleton = Singleton(WorkerRunner.get_lock_file(task, name))

	job_file = WorkerRunner.get_job_file(task, name)
	log_prefix = '[name=%(name)s interval=%(interval)s args=%(args)s]' % {
		'name': name,
		'interval': interval,
		'args': repr(tuple(sys.argv[4:])),
	}
	log(log_prefix + 'Task Start')

	def _do(job):
		log(log_prefix + 'Task Job Start=%s' % repr(job))
		result = generator.send(job)
		log(log_prefix + 'Task Job Result=%s' % repr(result))
		gc.set_debug(0)
		gc.collect()
		return result

	try:
		interval = float(interval)
		while True:
			job = None
			with MutexData(job_file) as d:
				if d.job and not d.result:
					result = _do(d.job)
					d.result = result or 'Worker Retired'
				elif d.queue:
					job = d.queue.pop(0)
				else:
					time.sleep(interval)
					continue
			if job: result = _do(job)
			if not result: break

		for _ in generator: pass
	except Exception as e:
		log(log_prefix + traceback.format_exc())
		log(log_prefix + str(e))

	os.remove(job_file)
	log(log_prefix + 'Task End')

def process():
	task_type, _, task = sys.argv[1].partition('_')
	openlog(task)

	try:
		# load module
		if task not in PROCESSORS:
			path = os.path.join(config.PROCESSOR, task + '.py')
			PROCESSORS[task] = imp.load_source(task, path)
	except Exception as e:
		log(traceback.format_exc())
		log(str(e))
		return

	if task_type == 'Runner':
		runner(task)
	elif task_type == 'Worker':
		worker(task)
	else:
		log('Bad task type: %s' % task_type)


def run_command(cmd):
	with MutexData(os.path.join(PROCESSOR_PATH, 'waiter.yml')) as d:
		if not d.process:
			d.process = [cmd]
		elif cmd not in d.process:
			d.process.append(cmd)

def waiter():
	interval = float(sys.argv[2]) if len(sys.argv) > 3 else 10
	singleton = Singleton(os.path.join(PROCESSOR_PATH, 'waiter.lock'))
	openlog('waiter')
	log('Waiter Start')

	try:
		while True:
			with MutexData(os.path.join(PROCESSOR_PATH, 'waiter.yml')) as d:
				while d.process:
					cmd = d.process.pop(0)
					log('Run: %s' % cmd)
					os.system(cmd)
			time.sleep(interval)
	except Exception as e:
		log(traceback.format_exc())
		log(str(e))

	log('Waiter End')

if __name__ == '__main__':
	if sys.argv[1] == 'waiter':
		waiter()
	else:
		process()
