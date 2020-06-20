SERVERPATH=$(cd `dirname $0`; pwd)
export PYTHONPATH="$SERVERPATH:$SERVERPATH/../thirdparty"

nohup python -B $SERVERPATH/process.py $1 $2 $3 $4 $5 $6 $7 $8 $9 </dev/null >/dev/null 2>&1 &
