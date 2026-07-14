/**
  ******************************************************************************
  * @file    linux_nucleo_i2c.c
  * @author  IMG SW Application Team
  * @brief   This file is part of the VD6283 Ultra Lite Driver 
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2020 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */

#include <fcntl.h> // open()
#include <unistd.h> // close()
#include <time.h> // clock_gettime()

#include <linux/i2c.h>
#include <linux/i2c-dev.h>

#include <sys/ioctl.h>

#include "linux_nucleo_i2c.h"
#include "types.h"

#define VD6283_ERROR_GPIO_SET_FAIL	-1
#define VD6283_COMMS_ERROR		    -2
#define VD6283_ERROR_TIME_OUT		-3

#define SUPPRESS_UNUSED_WARNING(x) \
	((void) (x))

#define VD6283_COMMS_CHUNK_SIZE  1024

#define ST_TOF_IOCTL_TRANSFER           _IOWR('a',0x1, void*)

#define LOG 				printf

#ifndef STMVL53L5CX_KERNEL
static uint8_t i2c_buffer[VD6283_COMMS_CHUNK_SIZE];
#else
struct comms_struct {
	uint16_t   len;
	uint16_t   reg_address;
	uint8_t    *buf;
	uint8_t    write_not_read;
};
#endif

int32_t vd6283_comms_init(VD6283_Platform * p_platform)
{


	p_platform->fd = open("/dev/i2c-1", O_RDWR);
	if (p_platform->fd == -1) {
		LOG("Failed to open /dev/i2c-1\n");
		return VD6283_COMMS_ERROR;
	}

	if (ioctl(p_platform->fd, I2C_SLAVE, 0x40) <0) {
		LOG("Could not speak to the device on the i2c bus\n");
		return VD6283_COMMS_ERROR;
	}

	LOG("Opened ST TOF Dev = %d\n", p_platform->fd);

	return 0;
}

int32_t vd6283_comms_close(VD6283_Platform * p_platform)
{
	close(p_platform->fd);
	return 0;
}


uint8_t RdByte(
		VD6283_Platform * p_platform,
		uint8_t reg_address,
		uint8_t *p_value)
{
	
	uint8_t outbuf[1], inbuf[1] , result;
    struct i2c_msg msgs[2];
    struct i2c_rdwr_ioctl_data msgset[1];

    outbuf[0] = reg_address;

    inbuf[0] = 0;

    msgs[0].addr = p_platform->address;
    msgs[0].flags = 0;
    msgs[0].len = 1;
    msgs[0].buf = outbuf;

    msgs[1].addr = p_platform->address;
    msgs[1].flags = I2C_M_RD | I2C_M_NOSTART;
    msgs[1].len = 1;
    msgs[1].buf = inbuf;

    msgset[0].msgs = msgs;
    msgset[0].nmsgs = 2;

    result = 0;
       

    if (ioctl(p_platform->fd, I2C_RDWR, &msgset) < 0) {
        perror("ioctl(I2C_RDWR) in i2c_read");
        return -1;
    }


	*p_value = inbuf[0];
    
	return result;
}

uint8_t WrByte(
		VD6283_Platform * p_platform,
		uint8_t reg_address,
		uint8_t value)
{
    int retval;
    uint8_t outbuf[2];

    struct i2c_msg msgs[1];
    struct i2c_rdwr_ioctl_data msgset[1];

    outbuf[0] = reg_address;
    outbuf[1] = value;

    msgs[0].addr = p_platform->address;
    msgs[0].flags = 0;
    msgs[0].len = 2;
    msgs[0].buf = outbuf;

    msgset[0].msgs = msgs;
    msgset[0].nmsgs = 1;

    if (ioctl(p_platform->fd, I2C_RDWR, &msgset) < 0) {
        perror("ioctl(I2C_RDWR) in i2c_write");
        return -1;
    }

    return 0;
}



uint8_t WaitMs(
		VD6283_Platform * p_platform,
		uint32_t time_ms)
{
	usleep(time_ms*1000);
	return 0;
}