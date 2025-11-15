caller_dir=$(pwd)
optional_arg=$2

if [[ $2 != "" && $2 != "." && $2 != "-oc" && $2 != "-nc" ]]
then
    caller_dir=$2
    optional_arg=$3
fi

pushd $(dirname $0)
XDG_SESSION_TYPE=xcb /home/mikkel/.local/bin/pdm run main.py "$caller_dir" $1 $optional_arg
popd
