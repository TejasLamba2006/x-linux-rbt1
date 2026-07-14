/**
 ******************************************************************************
 * @file    menu.c
 * @author  IMG SW Application Team
 * @brief   Main menu
 ******************************************************************************
 * @attention
 *
 * <h2><center>&copy; Copyright (c) 2015 STMicroelectronics.
 * All rights reserved.</center></h2>
 *
 * This software component is licensed by ST under BSD 3-Clause license,
 * the "License"; You may not use this file except in compliance with the
 * License. You may obtain a copy of the License at:
 *                        opensource.org/licenses/BSD-3-Clause
 *
 ******************************************************************************
 */


#include <unistd.h>
#include <signal.h>
#include <dlfcn.h>

#include <stdio.h>
#include <string.h>

#include "vl53l5cx_api.h"

#include "examples.h"

int exit_main_loop = 0;


int get_distance(VL53L5CX_Configuration *pDev);
int set_resolution(VL53L5CX_Configuration *pDev , uint8_t resolution);
int get_resolution(VL53L5CX_Configuration *pDev);
int set_ranging_frequency(VL53L5CX_Configuration *pDev,uint8_t	frequency_hz);
int get_ranging_frequency(VL53L5CX_Configuration *pDev);
int set_target(VL53L5CX_Configuration *pDev,uint8_t	target_order);
int get_target(VL53L5CX_Configuration *pDev);
int set_integration_time(VL53L5CX_Configuration *pDev,uint32_t integrtaion_time);
int get_integration_time(VL53L5CX_Configuration *pDev);
int set_power_down(VL53L5CX_Configuration *pDev, uint8_t pd_mode);
int get_power_down(VL53L5CX_Configuration *pDev);
int set_ranging_mode(VL53L5CX_Configuration *pDev,uint8_t mode);
int get_ranging_mode(VL53L5CX_Configuration *pDev);
int set_parameters(VL53L5CX_Configuration *pDev);

void sighandler(int signal)
{
	printf("SIGNAL Handler called, signal = %d\n", signal);
	exit_main_loop  = 1;
}

int gstatus = 0;
int main(int argc, char ** argv)
{
//	char choice[20];
	int status,option;
	VL53L5CX_Configuration 	Dev;

	/*********************************/
	/*   Power on sensor and init    */
	/*********************************/

	/* Initialize channel com */
	status = vl53l5cx_comms_init(&Dev.platform);
	if(status)
	{
		printf("VL53L5CX comms init failed\n");
		return -1;
	}

       option = atoi(argv[1]);

		switch(option)
		{

		case 1:
		status = get_distance(&Dev);
		break;

		case 2:
		status = set_resolution(&Dev,VL53L5CX_RESOLUTION_4X4);
		break;

		case 3:
		status = get_resolution(&Dev);
		break;

		case 4:
		/* Set ranging frequency to 10Hz.
			 * Using 4x4, min frequency is 1Hz and max is 60Hz
			 * Using 8x8, min frequency is 1Hz and max is 15Hz
	    */
		status = set_ranging_frequency(&Dev,10);
		break;

		case 5:
		status = get_ranging_frequency(&Dev);
		break;

		case 6:
		/* VL53L5CX_TARGET_ORDER_CLOSEST
			 VL53L5CX_TARGET_ORDER_STRONGEST
			 */

		status = set_target(&Dev,VL53L5CX_TARGET_ORDER_CLOSEST);
		break;

		case 7:
		status = get_target(&Dev);
		break;

		case 8:
		status = set_integration_time(&Dev,20);
		break;

		case 9:
		status = get_integration_time(&Dev);
		break;

		case 10:
		/*
		 VL53L5CX_POWER_MODE_WAKEUP
	 	VL53L5CX_POWER_MODE_SLEEP
		*/
		status = set_power_down(&Dev,VL53L5CX_POWER_MODE_SLEEP);
		break;

		case 11:
		status = get_power_down(&Dev);
		break;

		case 12:
		/*
				 VL53L5CX_RANGING_MODE_CONTINUOUS
		 		 VL53L5CX_RANGING_MODE_AUTONOMOUS
		*/
		status = set_ranging_mode(&Dev,VL53L5CX_RANGING_MODE_AUTONOMOUS);
		break;

		case 13:

		status = get_ranging_mode(&Dev);
		break;

		case 14:
		/* Set Default parameters*/
		status = set_parameters(&Dev);
		break;

    }
	vl53l5cx_comms_close(&Dev.platform);

	return 0;
}


int get_distance(VL53L5CX_Configuration *pDev)
{

	gstatus = example1(pDev);
	return gstatus ;
}


int set_resolution(VL53L5CX_Configuration *pDev , uint8_t resolution)
{
	printf("Setting resolution = %d \n",resolution);
	gstatus = vl53l5cx_set_resolution(pDev,resolution);
	return gstatus ;
}


int get_resolution(VL53L5CX_Configuration *pDev)
{
	uint8_t resolution;
	gstatus = vl53l5cx_get_resolution(pDev, &resolution);
	printf("resolution = %d \n",resolution);
	return gstatus ;
}


int set_ranging_frequency(VL53L5CX_Configuration *pDev,uint8_t	frequency_hz)
{
	printf("Setting ranging frequency = %d \n",frequency_hz);
	gstatus = vl53l5cx_set_ranging_frequency_hz(pDev,frequency_hz);
	return gstatus ;
}

int get_ranging_frequency(VL53L5CX_Configuration *pDev)
{
	uint8_t frequency;
	gstatus = vl53l5cx_get_ranging_frequency_hz(pDev, &frequency);
	printf("frequency = %d \n",frequency);
	return gstatus ;
}


int set_target(VL53L5CX_Configuration *pDev,uint8_t	target_order)
{
	printf("Setting target order = %d \n",target_order);
	gstatus = vl53l5cx_set_target_order(pDev,target_order);
	return gstatus ;
}


int get_target(VL53L5CX_Configuration *pDev)
{
	uint8_t target_order;
	gstatus = vl53l5cx_get_target_order(pDev, &target_order);
	printf("target_order = %d \n",target_order);
	return gstatus ;
}


int set_integration_time(VL53L5CX_Configuration *pDev,uint32_t integration_time)
{
	printf("Setting integration time = %d \n",integration_time);
	gstatus = vl53l5cx_set_integration_time_ms(pDev, integration_time);
	return gstatus ;
}


int get_integration_time(VL53L5CX_Configuration *pDev)
{
	uint32_t integration_time_ms;
	gstatus = vl53l5cx_get_integration_time_ms(pDev, &integration_time_ms);
	printf("integration_time_ms = %d \n",integration_time_ms);

	return gstatus ;
}


int set_power_down(VL53L5CX_Configuration *pDev,uint8_t pd_mode)
{
	printf("Setting power mode = %d \n",pd_mode);
	gstatus = vl53l5cx_set_power_mode(pDev, pd_mode);

	return gstatus ;
}



int get_power_down(VL53L5CX_Configuration *pDev)
{
	uint8_t current_power_mode;
	gstatus = vl53l5cx_get_power_mode(pDev, &current_power_mode);
	printf("current_power_mode = %d \n",current_power_mode);
	return gstatus ;
}


int set_ranging_mode(VL53L5CX_Configuration *pDev , uint8_t ranging_mode)
{
	printf("Setting ranging mode = %d \n",ranging_mode);
	gstatus = vl53l5cx_set_ranging_mode(pDev,ranging_mode);
	return gstatus ;
}


int get_ranging_mode(VL53L5CX_Configuration *pDev)
{
	uint8_t ranging_mode;
	gstatus = vl53l5cx_get_ranging_mode(pDev, &ranging_mode);
	printf("ranging_mode = %d \n",ranging_mode);
	return gstatus ;
}


int set_parameters(VL53L5CX_Configuration *pDev)
{
	printf("Setting default Parameters \n");
	gstatus = example2(pDev);
	return gstatus ;
}
