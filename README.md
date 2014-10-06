# Website converter

## Intro

Small python script for converting the old website content from [www repo](https://hg.adblockplus.org/www/) (Anwiki content mirror) to our [wwwnew repo](https://hg.adblockplus.org/wwwnew/) (our CMS).

convert.py was created by palant, being tweaked by kzar. Once adblockplus.org has been migrated to our CMS this script will have served it's purpose.

## Usage

The script assumes that the repos have been cloned with a directory structure like this:

      .
      ├── sitescripts
      ├── website-converter
      ├── www
      └── wwwnew

Just run `./convert.py` from the website-converter repo directory to convert the website content. To test the results run `python -m sitescripts.cms.bin.test_server .wwwnew/` from the sitescripts directory and browse to http://localhost:5000/ to see the results.
