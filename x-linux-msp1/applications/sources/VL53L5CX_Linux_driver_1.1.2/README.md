# STMICROELECTRONICS - VL53L5CX Linux driver
Official VL53L5CX Linux driver and test applications for linux and android platforms

## Introduction
The proposed implementation is customized to run on STM32MP platform, it has also been tested on a Raspberry Pi v3, but can be adapted to run on any linux embedded platform, as far as the VL53L5CX device is connected through I2C. The current package allows the user to compile and run this driver in a full user mode, where the i2c commnication is handled with the /dev/i2c-1 file descriptor. This needs the /dev/i2c-1 to be available which may not be the case on some secured platforms.

### compile the test examples, the platform adaptation layer and the uld driver
    $ nano vl53l5cx-uld-driver/user/test/Makefile
    $ cd vl53l5cx-driver/user/test
    $ make
### run the test application menu
    $ cd vl53l5cx-uld-driver/user/test
    $ ./menu

