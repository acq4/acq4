#!/usr/bin/python3

import time, socket


class NewScaleMPM():

    def __init__(self, ip_addr, port=23):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((ip_addr, port))
        self.sock.settimeout(1)

        self.origin = [7500., 7500., 7500.]

        try:
            for axis in ['x', 'y', 'z']:
                self.selectAxis(axis)
                self.setOrQueryDriveMode('closed')
                self.activateSoftLimits('deactivate')
        except socket.timeout:
            print('Socket timed out on Stage %s. No MPM connected?' % self.getIP())

    def close(self):
        self.sock.close()

    def getIP(self):
        return self.sock.getpeername()[0]

    """
    all commands listed in Section 8 of the Command and Control Reference Guide
    """

    # 01
    def readFirmwareVersion(self):
        """
        This command retrieves the version of the controller firmware.
        """
        cmd = "TR<01>\r"
        cmd_bytes = bytes(cmd, 'utf-8')
        self.sock.sendall(cmd_bytes)
        resp = self.sock.recv(1024).decode('utf-8').strip('<>\r')
        version = resp.split()[3]
        info = resp.split()[4]
        fw_version = '%s (%s)' % (version, info)
        return fw_version

    # 03
    def halt(self):
        """
        This command halts motor motion regardless of where the movement command
        was issued. If in closed-loop mode, the current position is now the target
        position.
        """
        cmd = "<03>\r"
        cmd_bytes = bytes(cmd, 'utf-8')
        self.sock.sendall(cmd_bytes)
        resp = self.sock.recv(1024) # no response after halt command?

    # 04
    def run(self, direction, duration_ds=None):
        """
        This command runs the motor. The motor will continue to move until command
        <03> is received or until an optional time value elapses. In closed-loop
        mode the motor will run according to PID, speed and acceleration settings.
        """
        if direction == 'forward':
            D = 1
        elif direction == 'backward':
            D = 0
        else:
            print('unrecognized direction')
            return
        TTTT = '' if duration_ds is None else '{0:04x}'.format(duration_ds)
        cmd = "<04 {0} {1}>\r".format(D, TTTT)
        cmd_bytes = bytes(cmd, 'utf-8')
        self.sock.sendall(cmd_bytes)
        resp = self.sock.recv(1024)

    # 05
    def moveTimedOpenLoopSteps(self, direction, SPT=None):
        """
        This command sends one or more bursts of resonant pulses to the motor at
        100 Hz (10 ms period) or at the period indicated by the PPPP parameter.
        By default, SPT=None means runs until halt. Otherwise,
            SPT = [nsteps, period, timeDuration]
        with period and timeDuration in units of 3.2us, and timeDuration < period
        """
        if direction == 'forward':
            D = 1
        elif direction == 'backward':
            D = 0
        else:
            print('unrecognized direction')
            return
        SSSS = '' if SPT is None else '{0:04x}'.format(SPT[0])
        PPPP = '' if SPT is None else '{0:04x}'.format(SPT[1])
        TTTT = '' if SPT is None else '{0:04x}'.format(SPT[2])
        cmd = "<05 {0} {1} {2} {3}>\r".format(D, SSSS, PPPP, TTTT)
        cmd_bytes = bytes(cmd, 'utf-8')
        self.sock.sendall(cmd_bytes)
        resp = self.sock.recv(1024)

    # 06
    def moveClosedLoopStep(self, direction, stepSize_counts=None):
        """
        This command adds or subtracts the specified step size (in encoder counts)
        to the current target position, and then moves the motor to the new target
        at the previously defined speed.
        ONLY VALID IN CLOSED LOOP MODE.
        """
        if direction == 'forward':
            D = 1
        elif direction == 'backward':
            D = 0
        else:
            print('unrecognized direction')
            return
        SSSSSSSS = '' if stepSize_counts is None else '{0:08x}'.format(int(stepSize_counts))
        cmd = "<06 {0} {1}>\r".format(D, SSSSSSSS)
        cmd_bytes = bytes(cmd, 'utf-8')
        self.sock.sendall(cmd_bytes)
        resp = self.sock.recv(1024)

    # 07
    def toggleAbsoluteRelative(self):
        """
        This command toggles the relative or absolute position modes. If the M3
        is currently in Absolute position mode, then the current reported position
        is set to 0.
        NOTE: is there really no way to do this idempotently? Or for that matter,
        to query the current status?
        """
        cmd = "<07>\r"
        cmd_bytes = bytes(cmd, 'utf-8')
        self.sock.sendall(cmd_bytes)
        resp = self.sock.recv(1024)

    # 08
    def moveToTarget(self, targetValue):
        """
        This command sets a target position and moves the motor to that target
        position at the speed defined by command <40>.
        ONLY VALID IN CLOSED-LOOP MODE.
        """
        targetValue = int(targetValue)
        cmd = "<08 {0:08x}>\r".format(targetValue)
        cmd_bytes = bytes(cmd, 'utf-8')
        self.sock.sendall(cmd_bytes)
        resp = self.sock.recv(1024)

    # 09
    def setOpenLoopSpeed(self, speed_255):
        """
        This command sets the open-loop speed of the motor, as a range from 0-255,
        with 255 representing 100% speed. This value is not saved to internal EEPROM.
        """
        speed_255 = int(speed_255)
        cmd = "<09 {0:02x}>\r".format(speed_255)
        cmd_bytes = bytes(cmd, 'utf-8')
        self.sock.sendall(cmd_bytes)
        resp = self.sock.recv(1024)

    # 10
    def viewClosedLoopStatus(self):
        """
        This command is used to view the motor status and position.
        """
        cmd = "<10>\r"
        cmd_bytes = bytes(cmd, 'utf-8')
        self.sock.sendall(cmd_bytes)
        resp = self.sock.recv(1024).decode('utf-8').strip('<>\r')
        SSSSSS = int(resp.split()[1], 16)
        PPPPPPPP = int(resp.split()[2], 16)
        EEEEEEEE = int(resp.split()[3], 16)
        return SSSSSS, PPPPPPPP, EEEEEEEE
        
    # 19
    def readMotorFlags(self):
        """
        This command reports internal flags used by the controller to monitor
        motor conditions.
        """
        cmd = "<19>\r"
        cmd_bytes = bytes(cmd, 'utf-8')
        self.sock.sendall(cmd_bytes)
        resp = self.sock.recv(1024).decode('utf-8').strip('<>\r')
        # TODO parse response
        
    # 20
    def setOrQueryDriveMode(self, mode, interval=None):
        """
        This command sets the drive mode for the M3. The M3 will always default
        to closed-loop mode on power up.
        """
        if mode == 'open':
            X = '0'
        elif mode == 'closed':
            X = '1'
        elif mode == 'query':
            X = 'R'
        else:
            print('unrecognized drive mode')
            return
        IIII = '' if interval is None else '0:04x'.format(int(interval))
        cmd = "<20 {0} {1}>\r".format(X, IIII)
        cmd_bytes = bytes(cmd, 'utf-8')
        self.sock.sendall(cmd_bytes)
        resp = self.sock.recv(1024).decode('utf-8').strip('<>\r')

    # 40
    # TODO set the closed-loop mode speed

    # 41
    # TODO set the position error thresholds and stall detection

    # 43
    # TODO view and set closed-loop PID coefficients

    # 46
    # TODO view and set forward and reverse soft limit values

    # 47
    def activateSoftLimits(self, action='query'):
        """
        This command is used to view, activate and deactivate motor travel limits.
        This command can disable the soft limits but the factory limits will remain
        active in both open- and closed-loop modes at all times. To define travel
        limits, use command <46...>. These values are saved to internal EEPROM.
        """
        if action == 'query':
            X = ''  # query
        elif action=='activate':
            X = ' 1'
        elif action=='deactivate':
            X = ' 0'
        else:
            print('unrecognized action')
            return
        cmd = "<47{0}>\r".format(X)
        cmd_bytes = bytes(cmd, 'utf-8')
        self.sock.sendall(cmd_bytes)
        resp = self.sock.recv(1024).decode('utf-8').strip('<>\r')
        #TODO parse response for query

    # 52
    # TODO view time interval units

    # 54
    # TODO get/set baud rate

    # 58
    # TODO supress/enable writes to eeprom

    # 74
    # TODO save closed-loop speed parameters to eeprom

    # 87
    def runFrequencyCalibration(self, direction, incremental=False, automatic=True,
                                frequncy_offset=None, ):
        """
        This command is used to optimize the Squiggle motor resonant drive frequency
        by, on command, sweeping over a range of frequencies, centered at the
        specified period, and settling on the frequency at which the best motor
        performance was detected. This command needs to be run at every power-up or
        more often in environments where the temperature is changing. When issuing
        an automatic frequency-calibration sweep command, the carriage may typically
        move 250 microns during the frequency sweep. If in closed-loop mode, the
        smart stage will return to the current target position automatically.
        It is best to run this command when system is idle and in the forward
        direction for the M3-LS-3.4 Linear Smart Stage.
        """
        if direction == 'forward':
            b0 = 1
        elif direction == 'backward':
            b0 = 0
        else:
            print('unrecognized direction')
            return
        b1 = 1 if incremental else 0
        b2 = 1 if automatic else 0
        D = (b2 << 2) | (b1 << 1) | (b0 << 0)
        XX = '' if frequency_offset is None else '0:02x'.format(int(frequency_offset))
        cmd = "<87 {0} {1}>\r".format(D, XX)
        cmd_bytes = bytes(cmd, 'utf-8')
        self.sock.sendall(cmd_bytes)
        resp = self.sock.recv(1024)


    #################################

    """
    higher-level commands
    """

    def selectAxis(self, axis):
        if (axis=='x') or (axis=='X'):
            cmd = b"TR<A0 01>\r"
        elif (axis=='y') or (axis=='Y'):
            cmd = b"TR<A0 02>\r"
        elif (axis=='z') or (axis=='Z'):
            cmd = b"TR<A0 03>\r"
        else:
            print('Error: axis not recognized')
            return
        self.sock.sendall(cmd)
        resp = self.sock.recv(1024)

    def querySelectedAxis(self):
        cmd = b"TR<A0>\r"
        self.sock.sendall(cmd)
        resp = self.sock.recv(1024)

    def moveToTarget3d_abs(self, x, y, z):
        """
        units are microns
        """
        # fire off each axis
        self.selectAxis('x')
        self.moveToTarget(x * 2)
        self.selectAxis('y')
        self.moveToTarget(y * 2)
        self.selectAxis('z')
        self.moveToTarget(z * 2)
        # now wait for all 3
        self.selectAxis('x')
        self.wait()
        self.selectAxis('y')
        self.wait()
        self.selectAxis('z')
        self.wait()

    def moveToTarget3d_rel(self, x, y, z):
        """
        units are microns
        """
        self.moveToTarget3d_abs(x-self.origin[0], y-self.origin[1], z-self.origin[2])

    def isMoving(self):
        SSSSSS, PPPPPPPP, EEEEEEEE = self.viewClosedLoopStatus()
        return bool(SSSSSS & (1 << 2))

    def wait(self):
        while self.isMoving():
            time.sleep(0.01)

    def getPosition_abs(self):
        self.selectAxis('x')
        x = self.viewClosedLoopStatus()[1]
        self.selectAxis('y')
        y = self.viewClosedLoopStatus()[1]
        self.selectAxis('z')
        z = self.viewClosedLoopStatus()[1]
        return x, y, z

    def getPosition_rel(self):
        """
        This is a software-defined relative positioning system.
        """
        x,y,z = self.getPosition_abs()
        return x-self.origin[0], y-self.origin[1], z-self.origin[2]

    def setOrigin(self, x, y, z):
        """
        Set the origin for relative positioning
        """
        self.origin = [x,y,z]


if __name__ == '__main__':
    import sys
    socket.setdefaulttimeout(1)

    ip_addr = sys.argv[1]
    stage = NewScaleMPM(ip_addr)
    print("Firmware version:", stage.readFirmwareVersion())
    print("Position:", stage.getPosition_abs())
    # stage.close()

