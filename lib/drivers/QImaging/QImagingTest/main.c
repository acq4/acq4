#include <stdio.h>
#include <QCamApi.h>

int main () {

	//Load driver and open the camera
	QCam_LoadDriver();
	Qcam_CamListItem	list[10];
	unsigned long		listLen = sizeof(list)/sizeof(list[Qcam_CamListItem]);
	QCam_ListCameras(list, &listLen);
	QCam_Handle			myHandle;
	QCam_OpenCamera(list[0].cameraId, &myHandle);
	
	//Read current settings
	QCam_Settings		mySettings;
	mySettings.size = sizeof(mySettings);
	QCam_ReadSettingsFromCam(myHandle, &mySettings);
	
	//Test Binning...this should work
	int a = QCam_IsParamSupported(myHandle, QCam_Param	QCam_qprmBinning);
	printf("IsBinningSupported=", a);
	int b = QCam_IsRangeTable(&mySettings, QCam_Param QCam_qprmBinning);
	printf("IsBinningRangeTable=", b);
	int c = QCam_IsSparseTable(&mySettings, QCam_Param QCam_qprmBinning);
	printf("IsBinningSparseTable=", c);
	
	//Test Readout Speed...in python readout speed is reported to be both a range and sparse table
	int d = QCam_IsParamSupported(myHandle, QCam_Param QCam_qprmReadoutSpeed);
	printf("IsReadoutSpeedSupported=", d);
	int e = QCam_IsRangeTable(&mySettings, QCam_Param QCam_qprmReadoutSpeed);
	printf("IsReadoutSpeedRangeTable=", e);
	int f = QCam_IsSparseTable(&mySettings, QCam_Param QCam_qprmReadoutSpeed);
	printf("IsReadoutSpeedSparseTable=", f);	
	
    return 0;
}
