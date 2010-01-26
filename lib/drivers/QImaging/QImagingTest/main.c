#include <stdio.h>
#include <QCam/QCamApi.h>

int main () {
	//Load driver and open the camera
	QCam_LoadDriver();
	QCam_CamListItem	list[10];
	unsigned long		listLen = 10;
	QCam_ListCameras(list, &listLen);
	QCam_Handle			myHandle;
	QCam_OpenCamera(list[0].cameraId, &myHandle);
	
	//Read current settings
	QCam_Settings		mySettings;
	mySettings.size = sizeof(mySettings);
	QCam_ReadSettingsFromCam(myHandle, &mySettings);
	
	//Test Binning...this should work
	int a = QCam_IsParamSupported(myHandle, qprmBinning);
	printf("IsBinningSupported=%d\n", a);
	int b = QCam_IsRangeTable(&mySettings, qprmBinning);
	printf("IsBinningRangeTable=%d\n", b);
	int c = QCam_IsSparseTable(&mySettings, qprmBinning);
	printf("IsBinningSparseTable=%d\n", c);
	
	//Test Readout Speed
	int d = QCam_IsParamSupported(myHandle, qprmReadoutSpeed);
	printf("IsReadoutSpeedSupported=%d\n", d);
	int e = QCam_IsRangeTable(&mySettings, qprmReadoutSpeed);
	printf("IsReadoutSpeedRangeTable=%d\n", e);
	int f = QCam_IsSparseTable(&mySettings, qprmReadoutSpeed);
	printf("IsReadoutSpeedSparseTable=%d\n", f);	
	unsigned long	utable[10];
	int	usize = 10;
	int k = QCam_GetParamSparseTable(&mySettings, qprmReadoutSpeed, utable, &usize);
	printf("ReadoutSpeedSparseTable (returned:%d): ", k);
	for(int i=0; i<usize; i++)
		printf(" %d", utable[i]);
	printf("\n");
	unsigned long min;
	QCam_GetParamMin(&mySettings, qprmReadoutSpeed, &min);
	printf("ReadoutSpeedMin = %d\n", min);
	unsigned long max;
	QCam_GetParamMax(&mySettings, qprmReadoutSpeed, &max);
	printf("ReadoutSpeedMax = %d\n", max);
	
	//Test Exposure
	int g = QCam_IsParamSupported(myHandle, qprmExposure);
	printf("IsExposureSupported=%d\n", g);
	int h = QCam_IsRangeTable(&mySettings, qprmExposure);
	printf("IsExposureRangeTable=%d\n", h);
	int j = QCam_IsSparseTable(&mySettings, qprmExposure);
	printf("IsExposureSparseTable=%d\n", j);	
	unsigned long	etable[10];
	int	esize = 10;
	int l = QCam_GetParamSparseTable(&mySettings, qprmExposure, etable, &esize);
	printf("ExposureSparseTable (returned:%d): ", l);
	for(int i=0; i<esize; i++)
		printf(" %d", etable[i]);
	printf("\n");
	QCam_GetParamMin(&mySettings, qprmExposure, &min);
	printf("ExposureMin = %d\n", min);
	QCam_GetParamMax(&mySettings, qprmExposure, &max);
	printf("ExposureMax = %d\n", max);
	
    return 0;
}
