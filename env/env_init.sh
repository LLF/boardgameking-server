#!/bin/sh

DBUSER="llf"
DBPASS="llf"

if [ $# -ne 1 ]; then
#    echo '指定引数が不正です' 1>&2
#    echo '実行するには設定ファイル名(.py抜き)を１つ渡してください' 1>&2
#    exit 1
    hostname=`hostname`
    cmd="print \$1 if /${hostname}/ .. /from / and /from\s(\S+)\s/"
    settings=`perl -ne "$cmd" ../application/settings/__init__.py`
else
    settings=$1
fi

echo "load settings = $settings"

echo "grant select,insert,delete,update,create,drop,file, alter,index on *.* to ${DBUSER}@localhost identified by '${DBPASS}';" | mysql -uroot -p

# pip
pip install -r ./pip_list > /dev/null &
cp ../tools/hooks/pre-commit.sample ../.git/hooks/pre-commit

# recreate db
DATABASE_NAMES=`python -c "from sets import Set;from ${settings} import DATABASES;print ' '.join(list(Set([db['NAME'] for db in DATABASES.values()])))"`
for db_name in ${DATABASE_NAMES}
do
    echo "drop and create database ${db_name}"
    echo "DROP DATABASE IF EXISTS \`${db_name}\`;CREATE DATABASE \`${db_name}\` DEFAULT CHARACTER SET utf8 COLLATE utf8_general_ci;" | mysql -u${DBUSER} -p${DBPASS}
done

# delete pyc
#find . -name '*.pyc' | xargs rm


# db migration
# db is stored in a hash, so the sort is not consistent. Here put the 'default' as the first one
DATABASE_ALIAS_NAMES=`python -c "from ${settings} import DATABASES;dbs = [db for db in DATABASES if db != 'read']; dbs.remove('default'); dbs = ['default'] + dbs; print ' '.join(dbs)"`

db_migration(){
    python ../application/manage.py migrate --settings=settings --database=${1}
    # python ../application/manage.py eventmodule migrate --settings=settings --database=${1}
    if [ ${1} == "default" ]; then
        ../data/sh/load_all.sh settings
    fi
}

for db_name in ${DATABASE_ALIAS_NAMES}
do
    echo "sync db: ${db_name}"
    python ../application/manage.py syncdb --noinput --settings=settings --database=${db_name}
    db_migration ${db_name}
done

echo "DB Initialzing was completed"

python ./manage.py update_cache_all --settings=settings

echo "data load was completed"

redis-cli "flushdb"
#./eventmodule/update.sh
