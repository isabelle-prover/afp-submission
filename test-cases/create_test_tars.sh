#!/bin/bash

# creates tar.gz files of example AFP theories residing in
# afp_submission/test-cases
# tar.gz files can be found in afp_submission/test-cases

# find directory where scripts and test-cases reside
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

cd $DIR
tar -zc Test1 > $DIR/test1.tar.gz
tar -zc Test2 > $DIR/test2.tar.gz
tar -zc Test3 > $DIR/test3.tar.gz
