import sys
import hashlib
import os
import sqlite3
import gnupg
from boto3.s3.transfer import S3Transfer
import boto3
workingpath = os.path.realpath(sys.path[0]) +"/"

# required pip packages   boto3, python-gnupg
# OS packages gpg
#
# there are two GPG pip packages please uninstall gnupg and install python-gnupg

# Warning, you will need freespace equal to or larger than the largest file you want to backup.

#Folders
foldertobackup = "/folder/to/backup/" # Change me - Must have tailing /
tempfolder=workingpath+"temp/"

#Database file
database=workingpath+"s3gpg.db"

#GPG Key
gpgkey=workingpath+"gpg.asc"
gpgrecipientaddress="you@email.com"

# AWS Info
AWS_ACCESS_KEY_ID = 'AWS ACCESS KEY' # Change me
AWS_SECRET_ACCESS_KEY = 'AWS SECRET ACCESS KEY' # Change me
bucket_name = "my-bucket" # Change me

# BUF_SIZE is totally arbitrary, change for your app!
BUF_SIZE = 65536  # lets read stuff in 64kb chunks!

#Folder Exists
if os.path.isdir(foldertobackup) == False:
        print("Backup Folder does not exist")
        quit()

#GPG Import Key
gpg = gnupg.GPG(gnupghome=workingpath+'GPG')
key_data = open(gpgkey).read()
import_result = gpg.import_keys(key_data)

#Setup database
conn = sqlite3.connect(database)
conn.text_factory = str
c = conn.cursor()
c2 = conn.cursor()
c.execute("create table if not exists files (file text,filename text,folder text, sha1 text, changed bool)")

#connect to AWS
client = boto3.client('s3', aws_access_key_id=AWS_ACCESS_KEY_ID,aws_secret_access_key=AWS_SECRET_ACCESS_KEY)
transfer = S3Transfer(client)

#check to see if any files have been deleted.
for row in c.execute('SELECT * FROM files'):
        if os.path.isfile(row[0]) == False:
            c2.execute("DELETE FROM files WHERE file = ?",(row[0],))
            s3folder = row[2].replace(foldertobackup,"")+"/"
            filename = row[1]
            if s3folder == "/":
                s3folder = ""
            client.delete_object(Bucket=bucket_name, Key=s3folder+filename+".gpg")

# commit our SQL Commands
conn.commit()

#check SHA1 Checksums of our files
for directory, subdirectories, files in os.walk(foldertobackup):
    for file in files:
        thefile = os.path.join(directory, file)
        sha1 = hashlib.sha1()
        if os.stat(thefile).st_size == 0:
            sha1hash = "emptyfile"
        else:
            with open(thefile, 'rb') as f:
                while True:
                    data = f.read(BUF_SIZE)
                    if not data:
                        break
                    sha1.update(data)
                    sha1hash = sha1.hexdigest()

        c.execute("SELECT sha1 FROM files WHERE file = ?",(thefile,))
        data=c.fetchone()
        if data is None:
            c.execute("INSERT INTO files VALUES (?,?,?,?,1)",(thefile,file,directory,sha1hash))
        else:
            if data[0] != sha1hash:
                c.execute("UPDATE files SET sha1=?, changed=1 WHERE file=?",(sha1hash,thefile))

# commit our SQL Commands
conn.commit()

for row in c.execute('SELECT * FROM files WHERE changed=1'):
        thefile = row[0]
        s3folder = row[2].replace(foldertobackup,"")+"/"
        filename = row[1]
        if s3folder == "/":
            s3folder = ""
        with open(thefile, 'rb') as f:
            status = gpg.encrypt_file(f, recipients=[gpgrecipientaddress],output=tempfolder+filename+".gpg",always_trust=True)
        #have all the variables populated which are required below
        transfer.upload_file(tempfolder+filename+".gpg", bucket_name, s3folder+filename+".gpg")
        os.remove(tempfolder+filename+".gpg")
        c2.execute("UPDATE files SET changed=0 WHERE file=?",(thefile,))

conn.commit()
c.close()
c2.close()
conn.close()

#upload database for safe keeping
transfer.upload_file(database, bucket_name, "s3gpg.db")