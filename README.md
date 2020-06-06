# <img src="https://raw.githack.com/FortAwesome/Font-Awesome/master/svgs/solid/robot.svg" card_color="#40DBB0" width="50" height="50" style="vertical-align:bottom"/> Wake Word
Just train a new wakeword
## !!!! caution first version many bugs
This skill is now one of the most complex skills I have ever done and not everything has been tested and works perfectly. I appreciate any feedback


## About
wakeword is only a few times spoken and bad detection sorted out. you could not do that through speech. i have thought about it and make a skill.
This skill should make it easier for everyone to use their own precise wake words and make it possible for everyone. you can also turn on a small webserver to check your audiofiles at http://mycroft_ip:8082

## Examples
* "I want to call you christopher"
* "install wakeword source"
* "You still do not understand me correctly"
* "I want to create my own model to Christopher"
* "I want to upload my wakeword Christopher"
* "I train 12 wacke word Christopher"
* "I train 12 no wacke word Christopher"


## Credits
gras64
## functionality
You say mycroft "I want to call you Christopher" and mycroft looks for a precise configuratios file. if under ./mycroft/precise and and in the skill folder no file is present starts learning. if there is a file, the configuration will be adjusted accordingly. You can also upgrade or upload your model to your repo and than to https://github.com/MycroftAI/Precise-Community-Data.git 


### configration
if you use Public Domain Sounds Backup it will take more then 1 GB space on disk for installation. use it cairfuly!!!
in the latest version i have set up a validator for the recording files. this can also be deactivated. you can also set up the number of samples to be recorded. you can also turn on a small webserver to check your audiofiles at http://mycroft_ip:8082

## To Do
* use of all operating systems an configurations
* debug
* upload to https://github.com/MycroftAI/Precise-Community-Data.git


## Category
**Configuration**
Productivity

## Tags
#Wake word

