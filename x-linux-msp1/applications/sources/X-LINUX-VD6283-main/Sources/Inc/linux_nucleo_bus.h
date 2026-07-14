
/**
  ******************************************************************************
  * @file           : stm32f4xx_nucleo_bus.h
  * @brief          : header file for the BSP BUS IO driver
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

/* Define to prevent recursive inclusion -------------------------------------*/
#ifndef STM32F4XX_NUCLEO_BUS_H
#define STM32F4XX_NUCLEO_BUS_H

#ifdef __cplusplus
 extern "C" {
#endif

/* Includes ------------------------------------------------------------------*/
#include "linux_nucleo_conf.h"
#include <stdint.h>
#include "linux_nucleo_errno.h"
#include "linux_nucleo_i2c.h"

/** @addtogroup BSP
  * @{
  */

/** @addtogroup STM32F4XX_NUCLEO
  * @{
  */

/** @defgroup STM32F4XX_NUCLEO_BUS STM32F4XX_NUCLEO BUS
  * @{
  */

/** @defgroup STM32F4XX_NUCLEO_BUS_Exported_Constants STM32F4XX_NUCLEO BUS Exported Constants
  * @{
  */

#define BUS_USART1_INSTANCE USART1
#define BUS_USART1_TX_GPIO_PIN GPIO_PIN_9
#define BUS_USART1_TX_GPIO_PORT GPIOA
#define BUS_USART1_TX_GPIO_CLK_ENABLE() __HAL_RCC_GPIOA_CLK_ENABLE()
#define BUS_USART1_TX_GPIO_CLK_DISABLE() __HAL_RCC_GPIOA_CLK_DISABLE()
#define BUS_USART1_TX_GPIO_AF GPIO_AF7_USART1
#define BUS_USART1_RX_GPIO_CLK_ENABLE() __HAL_RCC_GPIOA_CLK_ENABLE()
#define BUS_USART1_RX_GPIO_PORT GPIOA
#define BUS_USART1_RX_GPIO_CLK_DISABLE() __HAL_RCC_GPIOA_CLK_DISABLE()
#define BUS_USART1_RX_GPIO_PIN GPIO_PIN_10
#define BUS_USART1_RX_GPIO_AF GPIO_AF7_USART1

#ifndef BUS_USART1_BAUDRATE
   #define BUS_USART1_BAUDRATE  9600U /* baud rate of UARTn = 9600 baud*/
#endif
#ifndef BUS_USART1_POLL_TIMEOUT
   #define BUS_USART1_POLL_TIMEOUT                9600U
#endif

/**
  * @}
  */

/** @defgroup STM32F4XX_NUCLEO_BUS_Private_Types STM32F4XX_NUCLEO BUS Private types
  * @{
  */
#if (USE_HAL_UART_REGISTER_CALLBACKS  == 1U)
typedef struct
{
  pUART_CallbackTypeDef  pMspInitCb;
  pUART_CallbackTypeDef  pMspDeInitCb;
}BSP_UART_Cb_t;
#endif /* (USE_HAL_UART_REGISTER_CALLBACKS == 1U) */

/**
  * @}
  */

/** @defgroup STM32F4XX_NUCLEO_LOW_LEVEL_Exported_Variables LOW LEVEL Exported Constants
  * @{
  */

// extern UART_HandleTypeDef huart1;

/**
  * @}
  */

/** @addtogroup STM32F4XX_NUCLEO_BUS_Exported_Functions
  * @{
  */


/* BUS IO driver over I2C Peripheral */
int32_t BSP_I2C1_Init();
int32_t BSP_I2C1_DeInit(void);
int32_t BSP_I2C1_IsReady(uint16_t DevAddr, uint32_t Trials);
int32_t BSP_I2C1_WriteReg(uint16_t Addr, uint16_t Reg, uint8_t *pData, uint16_t Length);
int32_t BSP_I2C1_ReadReg(uint16_t Addr, uint16_t Reg, uint8_t *pData, uint16_t Length);
int32_t BSP_I2C1_WriteReg16(uint16_t Addr, uint16_t Reg, uint8_t *pData, uint16_t Length);
int32_t BSP_I2C1_ReadReg16(uint16_t Addr, uint16_t Reg, uint8_t *pData, uint16_t Length);
int32_t BSP_I2C1_Send(uint16_t DevAddr, uint8_t *pData, uint16_t Length);
int32_t BSP_I2C1_Recv(uint16_t DevAddr, uint8_t *pData, uint16_t Length);
int32_t BSP_I2C1_SendRecv(uint16_t DevAddr, uint8_t *pTxdata, uint8_t *pRxdata, uint16_t Length);
#if (USE_HAL_I2C_REGISTER_CALLBACKS == 1U)
int32_t BSP_I2C1_RegisterDefaultMspCallbacks (void);
int32_t BSP_I2C1_RegisterMspCallbacks (BSP_I2C_Cb_t *Callbacks);
#endif /* (USE_HAL_I2C_REGISTER_CALLBACKS == 1U) */

int32_t BSP_GetTick(void);


// HAL_StatusTypeDef MX_USART1_Init(UART_HandleTypeDef* huart);
int32_t BSP_USART1_Init(void);
int32_t BSP_USART1_DeInit(void);
int32_t BSP_USART1_Send(uint8_t *pData, uint16_t Length);
int32_t BSP_USART1_Recv(uint8_t *pData, uint16_t Length);
#if (USE_HAL_UART_REGISTER_CALLBACKS == 1U)
int32_t BSP_USART1_RegisterDefaultMspCallbacks (void);
int32_t BSP_USART1_RegisterMspCallbacks (BSP_UART_Cb_t *Callbacks);
#endif /* (USE_HAL_UART_REGISTER_CALLBACKS == 1U)  */

int32_t BSP_GetTick(void);


#ifdef __cplusplus
}
#endif

#endif /* STM32F4XX_NUCLEO_BUS_H */

   
