# Release Notes

### V 1.1.0 (13th May 2026)
**Minor release**
- Automated detection of PWM chip assignments based on timer memory addresses to handle variable probe orders on boot
- Updated deploy_starter_package.sh to copy the correct 6.6.116 kernel DTB from the package to the board's /boot/ folder
- Added a physical motor-to-STSPIN terminal wiring banner on application startup
- Added explicit support for Differential Drive steering alongside Mecanum wheel support


### V 1.0.0 (20th March 2025)
**First release** 
- API for dual STSPIN948 control
- APIs for ToF access
- Sensor fusion running on STM32MP to combine IMU and Magnetometer inputs
- Embedded Web sever and responsive web-client for remote control
- Validated on OpenSTLinux 6.0



