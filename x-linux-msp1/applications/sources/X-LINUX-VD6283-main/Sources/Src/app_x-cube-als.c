
/**
  ******************************************************************************
  * File Name          : app_x-cube-als.c
  * Description        : This file provides code for the configuration
  *                      of the STMicroelectronics.X-CUBE-ALS.1.0.0 instances.
  ******************************************************************************
  *
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

#ifdef __cplusplus
extern "C" {
#endif

/* Includes ------------------------------------------------------------------*/
#include "app_x-cube-als.h"
#include "main.h"
#include <stdio.h>

#include <math.h>
#include "6283a1_light_sensor.h"

/* Private typedef -----------------------------------------------------------*/
typedef struct
{
  double_t cct; /* cct (expressed in °K) */
  double_t X;
  double_t Y; /* illuminance (expressed in lux) */
  double_t Z;
} ResultCCT_t;

/* Private define ------------------------------------------------------------*/
#define LIGHT_SENSOR_INSTANCE_0 (0U)
#define CCT_COEFF_NB (3U)

/* Private variables ---------------------------------------------------------*/
static int32_t status = 0;
static uint8_t is_quit_requested;
static uint32_t AlsResults[LIGHT_SENSOR_MAX_CHANNELS] = {0};

volatile uint8_t ALS_EventDetected;

/* Private function prototypes -----------------------------------------------*/
static void MX_VD6283A1_LuxCCT_Init(void);
static void MX_VD6283A1_LuxCCT_Process(void);

static void compute_cct(uint32_t TimeExposure, ResultCCT_t *Result);
static void print_cct(ResultCCT_t *Result);
static int32_t decimal_partlux(double_t x);
static void decrease_exposure(uint8_t Instance);
static void increase_exposure(uint8_t Instance);
static void display_commands_banner(void);
static void handle_cmd(uint8_t cmd);
static uint8_t get_key(void);
static int32_t com_has_data(void);

void MX_X_CUBE_ALS_Init(void)
{
  /* Initialize the peripherals and the MEMS components */
  MX_VD6283A1_LuxCCT_Init();

}

/*
 * LM background task
 */
void MX_X_CUBE_ALS_Process(void)
{

  MX_VD6283A1_LuxCCT_Process();
}

static void MX_VD6283A1_LuxCCT_Init(void)
{
  /* Initialize Virtual COM Port */
//  BSP_COM_Init(COM1);
  display_commands_banner();
  status = VD6283A1_LIGHT_SENSOR_Init(LIGHT_SENSOR_INSTANCE_0);

  if (status)
  {
    printf("VD6283A1_LIGHT_SENSOR_Init failed\n");
    while(1);
  }
}

static void MX_VD6283A1_LuxCCT_Process(void)
{
  uint8_t channel;
  uint32_t current_exposure;

  ResultCCT_t CCT_Result;

  /* initialize exposure time */
  VD6283A1_LIGHT_SENSOR_SetExposureTime(LIGHT_SENSOR_INSTANCE_0, 100000); /* microseconds */
  VD6283A1_LIGHT_SENSOR_GetExposureTime(LIGHT_SENSOR_INSTANCE_0, &current_exposure);
 // printf("Exposure set to %lu us\n", (unsigned long)current_exposure);

  /* initialize gains */
  for (channel = 0; channel < LIGHT_SENSOR_MAX_CHANNELS; channel++)
  {
    VD6283A1_LIGHT_SENSOR_SetGain(LIGHT_SENSOR_INSTANCE_0, channel, 256);
  }

 // while (!is_quit_requested)
 // {
    VD6283A1_LIGHT_SENSOR_Start(LIGHT_SENSOR_INSTANCE_0, LIGHT_SENSOR_MODE_SINGLESHOT);

    /* poll for measurement */
    do {
      status = VD6283A1_LIGHT_SENSOR_GetValues(LIGHT_SENSOR_INSTANCE_0, AlsResults);
    //} while (status != BSP_ERROR_NONE);
    } while (status != 0);

    VD6283A1_LIGHT_SENSOR_Stop(LIGHT_SENSOR_INSTANCE_0);
    VD6283A1_LIGHT_SENSOR_GetExposureTime(LIGHT_SENSOR_INSTANCE_0, &current_exposure);

    compute_cct(current_exposure, &CCT_Result);
    print_cct(&CCT_Result);
    handle_cmd(get_key());
 // }

  VD6283A1_LIGHT_SENSOR_DeInit(LIGHT_SENSOR_INSTANCE_0);
  //printf("Quitting the demo...\n");
  //while (1);
}

/*
 * @brief compute cct value from RGB channels values
 */
static void compute_cct(uint32_t TimeExposure, ResultCCT_t *Result)
{
  /* correlation matrix used in order to convert RBG values to XYZ space */

  /*
   * (X)   (G)   (Cx1 Cx2 Cx3)
   * (Y) = (B) * (Cy1 Cy2 Cy3)
   * (Z)   (R)   (Cz1 Cz2 Cz3)
   *
   * X = G * Cx1 + B * Cx2 + R * Cx3
   * Y = G * Cy1 + B * Cy2 + R * Cy3
   * Z = G * Cz1 + B * Cz2 + R * Cz3
   *
   * */

  static const double_t Cx[] = {0.416700, -0.143816, 0.205570};
  static const double_t Cy[] = {0.506372, -0.120614, -0.028752};
  static const double_t Cz[] = {0.335866, 0.494781, -0.552625};

  uint8_t i;

  double_t data[CCT_COEFF_NB];
  double_t X_tmp = 0, Y_tmp = 0, Z_tmp = 0;
  double_t xyNormFactor;
  double_t m_xNormCoeff;
  double_t m_yNormCoeff;
  double_t nCoeff;
  double_t expo_scale = 100800.0 / TimeExposure;

  /* normalize and prepare RGB channels values for cct computation */
  data[0] = (double_t)AlsResults[LIGHT_SENSOR_GREEN_CHANNEL] / 256.0;
  data[1] = (double_t)AlsResults[LIGHT_SENSOR_BLUE_CHANNEL] / 256.0;
  data[2] = (double_t)AlsResults[LIGHT_SENSOR_RED_CHANNEL] / 256.0;

  /* apply correlation matrix to RGB channels to obtain (X,Y,Z) */
  for (i = 0; i < CCT_COEFF_NB; i++)
  {
    X_tmp += Cx[i] * data[i];
    Y_tmp += Cy[i] * data[i];
    Z_tmp += Cz[i] * data[i];
  }

  /* transform (X,Y,Z) to (x,y) */
  xyNormFactor = X_tmp + Y_tmp + Z_tmp;
  m_xNormCoeff = X_tmp / xyNormFactor;
  m_yNormCoeff = Y_tmp / xyNormFactor;

  /* rescale X, Y, Z according to expo. Reference is G1x and 100.8ms */
  Result->X = expo_scale * X_tmp;
  Result->Y = expo_scale * Y_tmp;
  Result->Z = expo_scale * Z_tmp;

  /* apply McCamy's formula to obtain CCT value (expressed in °K) */
  nCoeff = (m_xNormCoeff - 0.3320) / (0.1858 - m_yNormCoeff);
  Result->cct = (449 * pow(nCoeff, 3) + 3525 * pow(nCoeff, 2) + 6823.3 * nCoeff + 5520.33);
}

static void print_cct(ResultCCT_t *Result)
{
  /* clip the result in order to avoid negative values */
  if (Result->Y < 0) Result->Y = 0;

   //printf("LUX=%6ld ,CCT=%5ld K\n", (long)Result->Y,(long)Result->cct);
   printf("LUX= %d ,CCT= %d K\n", (long)Result->Y,(long)Result->cct);

//  printf("%6ld.%01ld Lux ", (long)Result->Y, (long)decimal_partlux(Result->Y));
//  printf("\tCCT: %5ld K\r", (long)Result->cct);
  fflush(stdout);
}

static int32_t decimal_partlux(double_t x)
{
  int32_t int_part = (int32_t) x;

  return (((int32_t) x - int_part) * 10);
}

/*
 * @brief divide exposure time by 2
 */
static void decrease_exposure(uint8_t Instance)
{
  uint32_t current_exposure;

  VD6283A1_LIGHT_SENSOR_GetExposureTime(Instance, &current_exposure);
  VD6283A1_LIGHT_SENSOR_SetExposureTime(Instance, current_exposure >> 1);
  VD6283A1_LIGHT_SENSOR_GetExposureTime(Instance, &current_exposure);
  printf("\nExposure set to %lu us\n", (unsigned long)current_exposure);
}

/*
 * @brief multiply exposure time by 2
 */
static void increase_exposure(uint8_t Instance)
{
  uint32_t current_exposure;

  VD6283A1_LIGHT_SENSOR_GetExposureTime(Instance, &current_exposure);
  VD6283A1_LIGHT_SENSOR_SetExposureTime(Instance, current_exposure << 1);
  VD6283A1_LIGHT_SENSOR_GetExposureTime(Instance, &current_exposure);
  printf("\nExposure set to %lu us\n", (unsigned long)current_exposure);
}

/*
 * @brief display application commands
 */
static void display_commands_banner(void)
{
}

/*
 * @brief process user command
 */
static void handle_cmd(uint8_t cmd)
{
  /* make sure the device is stopped before calling this function */
  switch (cmd)
  {
    case '4':
      decrease_exposure(LIGHT_SENSOR_INSTANCE_0);
      break;
    case '6':
      increase_exposure(LIGHT_SENSOR_INSTANCE_0);
      break;
    case 'q':
      is_quit_requested = 1;
      break;
  }
}

/*
 * @brief read new character from uart if availble
 */
static uint8_t get_key(void)
{
  uint8_t cmd = 0;

//  if (com_has_data())
 // {
  //  HAL_UART_Receive(&hcom_uart[COM1], &cmd, 1, HAL_MAX_DELAY);
 // }

  return cmd;
}

/*
 * @brief check if new data is available on uart
 */
static int32_t com_has_data(void)
{
//  return __HAL_UART_GET_FLAG(&hcom_uart[COM1], UART_FLAG_RXNE);;
}

#ifdef __cplusplus
}
#endif

   
