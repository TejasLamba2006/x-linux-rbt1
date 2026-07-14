/**
  ******************************************************************************
  * @file           : linux_nucleo_bus.c
  * @brief          : source file for the BSP BUS IO driver
  ******************************************************************************
  * @attention
  *
  *  Copyright (c) 2021 STMicroelectronics.
  * All rights reserved.  
  *
  * This software component is licensed by ST under Ultimate Liberty license
  * SLA0044, the "License"; You may not use this file except in compliance with
  * the License. You may obtain a copy of the License at:
  *                             www.st.com/SLA0044
  *
  ******************************************************************************
*/

/* Includes ------------------------------------------------------------------*/
#include "linux_nucleo_errno.h"
#include "linux_nucleo_bus.h"
#include <fcntl.h> // open()
#include <unistd.h> // close()
#include <linux/i2c.h>
#include <linux/i2c-dev.h>
#include <sys/ioctl.h> //ioctl
#include <stdio.h> //printf
#include <stdlib.h> //malloc

static uint8_t i2c_buf[1024];


/**
  * @}
  */

/** @defgroup STM32F4XX_NUCLEO_BUS_Private_Variables BUS Private Variables
  * @{
  */

static uint32_t I2C1InitCounter = 0;
static VD6283_Platform *plt ;
int fd = -1;

/* BUS IO driver over I2C Peripheral */
/*******************************************************************************
                            BUS OPERATIONS OVER I2C
*******************************************************************************/
/**
  * @brief  Initialize I2C HAL
  * @retval BSP status
  */
int32_t BSP_I2C1_Init()
{

  int32_t ret = BSP_ERROR_NONE;
  plt = (VD6283_Platform*)malloc(sizeof(VD6283_Platform));

  fd = open("/dev/i2c-1", O_RDWR);

	if (fd== -1) {
		printf("Failed to open /dev/i2c-1\n");
		ret =  -1;
	}
  // else{

  //   printf("device opened successfully %d \n",fd);
  // }

 
	if (ioctl(fd, I2C_SLAVE, 0x40) <0) {
		printf("Could not speak to the device on the i2c bus\n");
		return -2;
	}
  else
  {
	// printf("Openedd Color Sensor Dev = %d\n", fd);

   
  plt->address = 0x20;
  plt->fd = fd;

  
  }

    return ret;

}


/**
  * @brief  DeInitialize I2C HAL.
  * @retval BSP status
  */
int32_t BSP_I2C1_DeInit(void)
{
  int32_t ret = BSP_ERROR_NONE;

  return ret;
}

/**
  * @brief  Check whether the I2C bus is ready.
  * @param DevAddr : I2C device address
  * @param Trials : Check trials number
  *	@retval BSP status
  */
int32_t BSP_I2C1_IsReady(uint16_t DevAddr, uint32_t Trials)
{
  int32_t ret = BSP_ERROR_NONE;

  return ret;
}

/**
  * @brief  Write a value in a register of the device through BUS.
  * @param  DevAddr Device address on Bus.
  * @param  Reg    The target register address to write
  * @param  pData  Pointer to data buffer to write
  * @param  Length Data Length
  * @retval BSP status
  */
int32_t BSP_I2C1_WriteReg(uint16_t DevAddr, uint16_t Reg, uint8_t *pData, uint16_t Length)
{
  int32_t ret = BSP_ERROR_NONE;

  ret = WrByte(plt, Reg, *pData);

  return ret;
}

/**
  * @brief  Read a register of the device through BUS
  * @param  DevAddr Device address on Bus.
  * @param  Reg    The target register address to read
  * @param  pData  Pointer to data buffer to read
  * @param  Length Data Length
  * @retval BSP status
  */
int32_t  BSP_I2C1_ReadReg(uint16_t DevAddr, uint16_t Reg, uint8_t *pData, uint16_t Length)
{
  int32_t ret = BSP_ERROR_NONE;


  ret = RdByte(plt, Reg, pData);
  return ret;
}

/**
  * @brief  Return system tick in ms
  * @retval Current HAL time base time stamp
  */
int32_t BSP_GetTick(void) {
  return 1;
  //HAL_GetTick();
}

