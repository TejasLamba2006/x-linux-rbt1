# X-LINUX-RBT01 Web Application

This web application serves as client to the remote control applications server and provides a easy to use web based joystick interface to the user to control the movement and other funtionality of the rover. 


## Application Protocol 

In the current version of the application a JSON based protocol is used to control the rover.

The general format is as follows 

```json
{
    "subsystem":"9eda4b67-e287-48c1-9ed4-fedf3bf5a01a",
    "command":""
}

```