# Website converter

## Intro

Small python script for converting the old website content from [www repo](https://hg.adblockplus.org/www/) (Anwiki content mirror) to our [web.adblockplus.org repo](https://hg.adblockplus.org/web.adblockplus.org/) (our CMS).

`convert.py` was created by palant, being tweaked by kzar. Once adblockplus.org has been migrated to our CMS this script will have served it's purpose.

Also includes `refresh-static-files` script which makes refreshing some of the static files not updated elsewhere quicker.

## Usage

The script assumes that the repos have been cloned with a directory structure like this:

      .
      ├── sitescripts
      ├── website-converter
      ├── www
      └── web.adblockplus.org

Just run `./convert.py` from the website-converter repo directory to convert the website content. To test the results run `python -m sitescripts.cms.bin.test_server ../web.adblockplus.org/` from the sitescripts directory and browse to http://localhost:5000/ to see the results.

To update static files run `./refresh-static-files` from the website-converter repo directory.
