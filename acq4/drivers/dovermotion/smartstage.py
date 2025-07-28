from .control_thread import SmartStageControlThread


class SmartStage:
    def __init__(
            self,
            callback=None,
            poll_interval=0.05,
            callback_threshold=0.01,
            move_complete_threshold=0.01,
            default_acceleration=10.0,
    ):
        self.default_acceleration = default_acceleration
        self.control_thread = SmartStageControlThread(
            callback, poll_interval, callback_threshold, move_complete_threshold)

    def stop(self):
        """Stop the device immediately"""
        return self.control_thread.request('stop')

    def move(self, pos, speed, acceleration=None):
        """Move to a position and return a SmartStageRequestFuture.
        
        Parameters
        ----------
        pos : sequence of float
            The target position for each axis in mm. If None, that axis will not move.
        speed : float
            The speed to move at in mm/s.
        acceleration : float | None
            The acceleration to use in mm/s^2. If None, the default acceleration is used.
        """
        if acceleration is None:
            acceleration = self.default_acceleration
        return self.control_thread.request('move', pos=pos, speed=speed, acceleration=acceleration)

    def quit(self):
        """Quit the control thread"""
        return self.control_thread.request('quit')

    def enable(self):
        return self.control_thread.request('enable')

    def disable(self):
        return self.control_thread.request('disable')

    def pos(self, refresh=False):
        if refresh:
            return self.control_thread.request('position').result()
        else:
            return self.control_thread.last_pos

    def stop(self):
        return self.control_thread.request('stop')


if __name__ == "__main__":
    import argparse
    import pyqtgraph as pg
    import acq4.drivers.dovermotion.motionsynergy_api as ms_server

    app = pg.mkQApp()
    print("app!")

    parser = argparse.ArgumentParser(description="Access MotionSynergyAPI from python prompt")
    parser.add_argument("--dll", type=str, help="Path to the MotionSynergyAPI.dll file")
    args = parser.parse_args()

    ms_server.install_tray_icon()
    motionSynergy, instrumentSettings = ms_server.get_motionsynergyapi(args.dll)


    def pos_cb(pos):
        print("Position change:", pos)


    ss = SmartStage(callback=pos_cb)

#     parser.add_argument("--port", type=int, default=60738, help="Port to listen on")
#     parser.add_argument("--no-init", action="store_true", help="Do not initialize the MotionSynergyAPI")
#     args = parser.parse_args()

#     path = "C:\\Users\\lukec\\Desktop\\Devices\\Dover Stages\\MotionSynergyAPI_SourceCode_3.6.12025\\"
#     motionSynergy, instrumentSettings = get_motionsynergyapi(path + "MotionSynergyAPI.dll")
#     configure(motionSynergy, instrumentSettings)
#     if not args.no_init:
#         initialize()

#     server = teleprox.RPCServer(address=f"tcp://127.0.0.1:{args.port}")
#     server['motionSynergy'] = motionSynergy
#     server['instrumentSettings'] = instrumentSettings
#     server.run_forever()


# print("Current position:", pos())


# Perform a series of moves, appropriate for the selected product.
# These moves are wrapped in a try / catch block to ensure Shutdown is called prior to
# exit, ensuring each axis is disabled on exit.
# try:
#     if productType == "SmartStageLinear":
#         from SmartStageLinear import *
#         smartStage = SmartStageLinear(axes[0], motionSynergy.Diagnostics)
#         smartStage.PerformMoves()
#     elif productType == "SmartStageXY":
#         from SmartStageXY import *
#         smartStage = SmartStageXY(axes[0], axes[1], motionSynergy.Diagnostics)
#         smartStage.PerformMoves()
#     elif productType == "DOF5":
#         from DOF5 import *
#         dof5 = DOF5(axes[0], motionSynergy.Diagnostics)
#         dof5.PerformMoves()
#     elif productType == "DMCM":
#         from DMCM import *
#         dmcm = DMCM(axes[0], motionSynergy.Diagnostics)
#         dmcm.PerformMoves()
#     else:
#         print(
#             f"Unknown ProductType {productType} specified in configuration file {instrumentSettings.ConfigurationFilename}.")
# except Exception as e:
#     print(repr(e))


# Things we can do with axes  (all methods return a future-like object)

# result = axis.MoveAbsolute(mm)
# result.Wait()
# result.Alert  # cause of failure
# result.Success  # bool
# result.ToString()  # for debugging
# axis.MoveContinuous  # move to absolute position; can be called while already in motion
# axis.GetActualPosition().Value
# axis.Stop()
# axis.Get/SetVelocity  # max velocity, not current velocity
# axis.Get/SetAcceleration
# axis.Get/SetDeceleration
# axis.Get/SetJerk
# axis.GetMotorCurrent
# axis.Disable()  # de-energize motor
# axis.Enable()   # energize motor
