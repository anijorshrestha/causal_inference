import subprocess
import os
import shutil


def convert():
    # Run owl2vowl.jar converter : convert ontology file TTL to JSON format supported by WebVOWL
    proc = subprocess.Popen(
        "java -jar ../api/static/owl2vowl.jar -file ../api/static/ontology/YOUR_ONTOLOGY.owl", shell=True,
        stdout=subprocess.PIPE)

    # Move generated JSON file to data dir
    source = '../YOUR_ONTOLOGY.json'
    destination = '../api/static/ontology/YOUR_ONTOLOGY.json'
    if os.path.exists(source):
        dest = shutil.move(source, destination)