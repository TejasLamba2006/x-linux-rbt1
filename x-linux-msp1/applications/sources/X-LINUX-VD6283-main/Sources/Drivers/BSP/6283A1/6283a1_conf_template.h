/**
 ******************************************************************************
 * @file    6283a1_conf_template.h
 * @author  IMG SW Application Team
 * @brief   This file contains definitions for the ALS components bus interfaces
 *          when using the X-NUCLEO-6283A1 expansion board
 *          This file should be copied to the application folder and renamed
 *          to 6283a1_conf.h.
 ******************************************************************************
 * @attention
 *
 *  Copyright (c) 2021 STMicroelectronics.
 * All rights reserved.  
 *
 * This software is licensed under terms that can be found in the LICENSE file
 * in the root directory of this software component.
 * If no LICENSE file comes with this software, it is provided AS-IS.
 *
 ******************************************************************************
 */

#ifndef VD6283A1_CONF_H
#define VD6283A1_CONF_H

#ifdef __cplusplus
extern "C" {
#endif

#define LIGHT_SENSOR_INSTANCES_NBR      (1U)

#define VD6283A1_I2C_SCL_GPIO_PORT      BUS_I2C1_SCL_GPIO_PORT
#define VD6283A1_I2C_SCL_GPIO_PIN       BUS_I2C1_SCL_GPIO_PIN
#define VD6283A1_I2C_SDA_GPIO_PORT      BUS_I2C1_SDA_GPIO_PORT
#define VD6283A1_I2C_SDA_GPIO_PIN       BUS_I2C1_SDA_GPIO_PIN

#define VD6283A1_I2C_Init               BSP_I2C1_Init
#define VD6283A1_I2C_DeInit             BSP_I2C1_DeInit
#define VD6283A1_I2C_WriteReg           BSP_I2C1_WriteReg
#define VD6283A1_I2C_ReadReg            BSP_I2C1_ReadReg
#define VD6283A1_GetTick                BSP_GetTick

#ifdef __cplusplus
}
#endif

#endif /* VD6283A1_CONF_H */

   

