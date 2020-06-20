# web server

#### **nginx**

1. `yum install -y nginx`

2. `vi /etc/nginx/nginx.conf`

```
user username;

#        location / {
#        }
```

3. Make symbolic link to nginx.conf

```
mkdir /etc/nginx/default.d
cd /etc/nginx/default.d
ln -s /home/username/PerfPipe/server/nginx.conf PerfPipe.conf
```

4. systemctl restart nginx


#### **uwsgi**

`pip install uwsgi`

```
uwsgi --ini /home/username/PerfPipe/server/uwsgi.ini
uwsgi --reload /home/username/PerfPipe/server/uwsgi.pid
uwsgi --stop /home/username/PerfPipe/server/uwsgi.pid
```

#### **rsyslog**

1. `vi /etc/rsyslog.d/processor.conf`

```
$template ProcessorFile,"/var/log/processor-%syslogtag:R,ERE,1,DFLT:\[([0-9a-zA-Z]+)\]--end%"
:programname, isequal, "Processor"	action(type="omfile"
	FileOwner="username"
	FileGroup="username"
	DynaFile="ProcessorFile")
& ~
```

2. `systemctl restart rsyslog`
