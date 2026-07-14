# X-LINUX-VD6283
X-LUNX Software Package for VD6283TX Hybrid filter multispectral sensor with light flicker engine
https://www.st.com/en/imaging-and-photonics-solutions/vd6283tx.html


#Before Running make command make sure to export the tool chain correctly , for STM32MP1 install the SDK first and source it : 
https://wiki.st.com/stm32mpu/wiki/Getting_started/STM32MP1_boards/STM32MP157x-EV1/Develop_on_Arm%C2%AE_Cortex%C2%AE-A7/Install_the_SDK


#To build the Application enter in the Directory havign Makefile and do make 
$make
#built application will be formed in the same directory with name vd6283 , transfer it to STM32MP1 and run i tusing ./vd6283,X-NUCLEO-VD6283A1 must be connected to arduino connector 
on STM32MP1 board with i2c5 enabled in the dts arch/arm/boot/stm32mp157f-dk2.dts

&i2c5{

	status = "okay"

};



#follow this to build the device tree : https://wiki.st.com/stm32mpu/wiki/Getting_started/STM32MP1_boards/STM32MP157x-EV1/Develop_on_Arm%C2%AE_Cortex%C2%AE-A7/Modify,_rebuild_and_reload_the_Linux%C2%AE_kernel

make ARCH=arm dtbs


#transfer this dtb to /boot of stm32mp1
