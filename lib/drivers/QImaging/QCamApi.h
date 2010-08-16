/*
|==============================================================================
| Copyright (C) 2007 Quantitative Imaging Corporation.  All Rights Reserved.
| Reproduction or disclosure of this file or its contents without the prior
| written consent of Quantitative Imaging Corporation is prohibited.
|==============================================================================
|
| File:			QCamApi.h
|
| Project/lib:	QCam Driver
|
| Targets:		Mac OS X, Windows, Linux
|
| Description:	Header file for the QCam API
|
| Notes:		This interface is not reentrant.  
|				See "QCam API.pdf" for more details.
|
|=======*/

#pragma warning (disable: 4068)

#pragma mark DEFINES

#ifndef QCAMAPI_H_INCLUDE
#define QCAMAPI_H_INCLUDE

#ifndef QCAMAPI
	#ifdef _WIN32
		#define QCAMAPI __stdcall
		#define UNSIGNED64 unsigned __int64
	#else
		#define QCAMAPI
		#define UNSIGNED64 unsigned long long
	#endif
#endif // QCAMAPI

#ifdef __cplusplus
extern "C" {
#endif


#define QCAMAPI_VERSION		(2008)



#pragma mark ENUMS

// Camera Model
//
typedef enum
{
	// Legacy hardware
	qcCameraUnknown			= 0,
	qcCameraMi2				= 1,		// MicroImager II and Retiga 1300
	qcCameraPmi				= 2,
	qcCameraRet1350			= 3,		// Retiga EX
	qcCameraQICam			= 4,

	// Current hardware
	qcCameraRet1300B		= 5,
	qcCameraRet1350B		= 6,		// Retiga EXi
	qcCameraQICamB			= 7,		// QICam
	qcCameraMicroPub		= 8,		// Micropublisher
										// (returns this for both legacy
										// and current models)
	qcCameraRetIT		 	= 9,
	qcCameraQICamIR			= 10,		// QICam IR
	qcCameraRochester		= 11,
	
	qcCameraRet4000R		= 12,		// Retiga 4000R
	
	qcCameraRet2000R		= 13,		// Retiga 2000R
	
	qcCameraRoleraXR		= 14,		// Rolera XR
	
	qcCameraRetigaSRV		= 15,		// Retiga SRV
	
	
	qcCameraOem3			= 16,
	
	qcCameraRoleraMGi		= 17,		// Rolera MGi
	
	qcCameraRet4000RV		= 18,		// Retiga 4000RV

	qcCameraRet2000RV		= 19,		// Retiga 2000RV

	qcCameraOem4			= 20,

	qcCameraGo1				= 21,		// USB CMOS camera

	qcCameraGo3				= 22,		// USB CMOS camera

	qcCameraGo5				= 23,		// USB CMOS camera

	qcCameraGo21			= 24,		// USB CMOS camera

	qcCameraRoleraEMC2		= 25,		
	
	qcCameraRetigaEXL		= 26,		
	
	qcCameraRoleraXRL		= 27,		
	
	qcCameraRetigaSRVL		= 28,

	qcCameraRetiga4000DC	= 29,

	qcCameraRetiga2000DC	= 30,

	qcCameraEXiBlue			= 31,

	qcCameraEXiGreen		= 32,

	qcCameraRetigaIndigo	= 33,

	// Reserved numbers
	qcCameraX				= 1000,
	qcCameraOem1			= 1001,
	qcCameraOem2			= 1002
}
QCam_qcCameraType;


// CCD Type
//
typedef enum
{
	qcCcdMonochrome		= 0,
	qcCcdColorBayer		= 1,
	qctype_last			= 2
}
QCam_qcCcdType;


// CCD Model
//
// Kodak type keys: (qcCcdKAI...)
//  "C"			Color (absense indicates monochrome)
//  "M"			Microlens
//  "g"			Glass types (letters following "g")
//	"AR"		Antireflective
//	"C"			Clear
//	"Q"			Quartz
//	"N"			None (an unsealed CCD)

typedef enum
{
	qcCcdKAF1400		= 0,
	qcCcdKAF1600		= 1,
	qcCcdKAF1600L		= 2,
	qcCcdKAF4200		= 3,
	qcCcdICX085AL		= 4,
	qcCcdICX085AK		= 5,
	qcCcdICX285AL		= 6,
	qcCcdICX285AK		= 7,
	qcCcdICX205AL		= 8,
	qcCcdICX205AK		= 9,
	qcCcdICX252AQ		= 10,
	qcCcdS70311006		= 11,
	qcCcdICX282AQ		= 12,
	qcCcdICX407AL		= 13,
	qcCcdS70310908		= 14,
	qcCcdVQE3618L		= 15,
	qcCcdKAI2001gQ		= 16,
	qcCcdKAI2001gN		= 17,
	qcCcdKAI2001MgAR	= 18,
	qcCcdKAI2001CMgAR	= 19,
	qcCcdKAI4020gN		= 20,
	qcCcdKAI4020MgAR	= 21,
	qcCcdKAI4020MgN		= 22,
	qcCcdKAI4020CMgAR	= 23,
	qcCcdKAI1020gN		= 24,
	qcCcdKAI1020MgAR	= 25,
	qcCcdKAI1020MgC		= 26,
	qcCcdKAI1020CMgAR	= 27,
	qcCcdKAI2001MgC		= 28,
	qcCcdKAI2001gAR		= 29,
	qcCcdKAI2001gC		= 30,
	qcCcdKAI2001MgN		= 31,
	qcCcdKAI2001CMgC	= 32,
	qcCcdKAI2001CMgN	= 33,
	qcCcdKAI4020MgC		= 34,
	qcCcdKAI4020gAR		= 35,
	qcCcdKAI4020gQ		= 36,
	qcCcdKAI4020gC		= 37,
	qcCcdKAI4020CMgC	= 38,
	qcCcdKAI4020CMgN	= 39,
	qcCcdKAI1020gAR		= 40,
	qcCcdKAI1020gQ		= 41,
	qcCcdKAI1020gC		= 42,
	qcCcdKAI1020MgN		= 43,
	qcCcdKAI1020CMgC	= 44,
	qcCcdKAI1020CMgN	= 45,

	qcCcdKAI2020MgAR	= 46,
	qcCcdKAI2020MgC		= 47,
	qcCcdKAI2020gAR		= 48,
	qcCcdKAI2020gQ		= 49,
	qcCcdKAI2020gC		= 50,
	qcCcdKAI2020MgN		= 51,
	qcCcdKAI2020gN		= 52,
	qcCcdKAI2020CMgAR	= 53,
	qcCcdKAI2020CMgC	= 54,
	qcCcdKAI2020CMgN	= 55,

	qcCcdKAI2021MgC		= 56,
	qcCcdKAI2021CMgC	= 57,
	qcCcdKAI2021MgAR	= 58,
	qcCcdKAI2021CMgAR	= 59,
	qcCcdKAI2021gAR		= 60,
	qcCcdKAI2021gQ		= 61,
	qcCcdKAI2021gC		= 62,
	qcCcdKAI2021gN		= 63,
	qcCcdKAI2021MgN		= 64,
	qcCcdKAI2021CMgN	= 65,

	qcCcdKAI4021MgC		= 66,
	qcCcdKAI4021CMgC	= 67,
	qcCcdKAI4021MgAR	= 68,
	qcCcdKAI4021CMgAR	= 69,
	qcCcdKAI4021gAR		= 70,
	qcCcdKAI4021gQ		= 71,
	qcCcdKAI4021gC		= 72,
	qcCcdKAI4021gN		= 73,
	qcCcdKAI4021MgN		= 74,
	qcCcdKAI4021CMgN	= 75,
	qcCcdKAF3200M		= 76,
	qcCcdKAF3200ME		= 77,
	qcCcdE2v97B			= 78,
	qcCMOS				= 79,
	qcCcdTX285			= 80,

	qcCcdKAI04022MgC	= 81,
	qcCcdKAI04022CMgC	= 82,
	qcCcdKAI04022MgAR	= 83,
	qcCcdKAI04022CMgAR	= 83,
	qcCcdKAI04022gAR	= 85,
	qcCcdKAI04022gQ		= 86,
	qcCcdKAI04022gC		= 87,
	qcCcdKAI04022gN		= 88,
	qcCcdKAI04022MgN	= 89,
	qcCcdKAI04022CMgN	= 90,

	qcCcd_last			= 91,
	qcCcdX				= 255	// Reserved 
}
QCam_qcCcd;


// Intensifier Model
//
typedef enum
{
	qcItVsStdGenIIIA	= 0,
	qcItVsEbGenIIIA		= 1,
	qcIt_last			= 2
}
QCam_qcIntensifierModel;


// Bayer Pattern
//
typedef enum
{
	qcBayerRGGB			= 0,
	qcBayerGRBG			= 1,
	qcBayerGBRG			= 2,
	qcBayerBGGR			= 3,
	qcBayer_last		= 4
}
QCam_qcBayerPattern;


// Trigger Type
//
typedef enum
{
	qcTriggerNone		= 0,		// Depreciated

	// Freerun mode: expose images as fast as possible
	qcTriggerFreerun	= 0,

	// Hardware trigger modes
	qcTriggerEdgeHi		= 1,		// Edge triggers exposure start
	qcTriggerEdgeLow	= 2,
	qcTriggerPulseHi	= 3,		// Integrate over pulse
	qcTriggerPulseLow	= 4,

	// Software trigger (trigger through API call)
	qcTriggerSoftware	= 5,

	// New hardware trigger modes
	qcTriggerStrobeHi	= 6,		// Integrate over pulse without masking
	qcTriggerStrobeLow	= 7,

	qcTrigger_last		= 8
}
QCam_qcTriggerType;


// RGB Filter Wheel Color
//
typedef enum
{
	qcWheelRed			= 0,
	qcWheelGreen		= 1,
	qcWheelBlack		= 2,
	qcWheelBlue			= 3,
	qcWheel_last		= 4
}
QCam_qcWheelColor;


// Readout Speed
//
typedef enum
{
	qcReadout20M		= 0,
	qcReadout10M		= 1,
	qcReadout5M			= 2,
	qcReadout2M5		= 3,
	qcReadout1M			= 4,
	qcReadout24M		= 5,
	qcReadout48M		= 6,
	qcReadout40M		= 7,
	qcReadout30M		= 8,
	qcReadout_last		= 9
}
QCam_qcReadoutSpeed;


// Readout port
typedef enum
{
	qcPortNormal		= 0,
	qcPortEM			= 1,
	qcReadoutPort_last	= 2
}
QCam_qcReadoutPort;


// Shutter Control
//
typedef enum
{
	qcShutterAuto		= 0,
	qcShutterClose		= 1,
	qcShutterOpen		= 2,
	qcShutter_last		= 3
}
QCam_qcShutterControl;


// Output on the SyncB Port
//
typedef enum
{
	qcSyncbTrigmask		= 0,
	qcSyncbExpose		= 1,
	qcSyncbOem1			= 0,
	qcSyncbOem2			= 1,
	qcSyncb_last		= 2
}
QCam_qcSyncb;


// Callback Flags
//
typedef enum
{
	qcCallbackDone			= 1,	// Callback when QueueFrame (or QueueSettings) is done
	qcCallbackExposeDone	= 2		// Callback when exposure is done (readout starts)
									// - For cameras manufactured after March 1, 2004 and all MicroPublishers
									// - This callback is not guaranteed to occur
}
QCam_qcCallbackFlags;


// RTV Mode
//
typedef enum
{
	qmdStandard				= 0,	// Default camera mode
	qmdRealTimeViewing		= 1,	// Real Time Viewing (RTV) mode, for MicroPublisher only
	qmdOverSample			= 2,	// A mode where you may snap Oversampled images from supported cameras
	qmd_last				= 3,
	_qmd_force32			= 0xFFFFFFFF
}
QCam_Mode;


// CCD Clearing Mode
typedef enum
{
	qcPreFrameClearing		= 0,	// Default mode, clear CCD before next exposure starts 
	qcNonClearing			= 1		// Do not clear CCD before next exposure starts
}
QCam_qcCCDClearingModes;


// Fan Control Speed
//
typedef enum
{
	qcFanSpeedLow			= 1,
	qcFanSpeedMedium		= 2,
	qcFanSpeedHigh			= 3,
	qcFanSpeedFull			= 4
}
QCam_qcFanSpeed;


// Image Format
//
// The name of the RGB format indicates how to interpret the data.
// Example: Xrgb32 means the following:
// Byte 1: Alpha (filled to be opaque, since it's not used)
// Byte 2: Red
// Byte 3: Green
// Byte 4: Blue
// The 32 corresponds to 32 bits (4 bytes)
//
// Note: The endianess of the data will be consistent with
// the processor used.
// x86/x64 = Little Endian
// PowerPC = Big Endian
// More information can be found at http://en.wikipedia.org/wiki/Endianness 
//
// Note: - On color CCDs, 1x1 binning requires a bayer format (ex: qfmtBayer8)
//       - On color CCDs, binning higher than 1x1 requires a mono format (ex: qfmtMono8)
//       - Choosing a color format on a mono CCD will return a 3-shot RGB filter image
//
typedef enum
{
	qfmtRaw8				= 0,	// Raw CCD output (this format is not supported)
	qfmtRaw16				= 1,	// Raw CCD output (this format is not supported)
	qfmtMono8				= 2,	// Data is bytes
	qfmtMono16				= 3,	// Data is shorts, LSB aligned
	qfmtBayer8				= 4,	// Bayer mosaic; data is bytes
	qfmtBayer16				= 5,	// Bayer mosaic; data is shorts, LSB aligned
	qfmtRgbPlane8			= 6,	// Separate color planes
	qfmtRgbPlane16			= 7,	// Separate color planes
	qfmtBgr24				= 8,	// Common Windows format
	qfmtXrgb32				= 9,	// Format of Mac pixelmap
	qfmtRgb48				= 10,
	qfmtBgrx32				= 11,	// Common Windows format
	qfmtRgb24				= 12,	// RGB with no alpha
	qfmt_last				= 13
}
QCam_ImageFormat;


// Camera Parameters - Unsigned 32 bit
//
// For use with QCam_GetParam, 
//				QCam_GetParamMin
//				QCam_GetParamMax
//				QCam_SetParam
//				QCam_GetParamSparseTable
//				QCam_IsSparseTable
//				QCam_IsRangeTable
//				QCam_IsParamSupported
//
// Note: Cameras produced after Mar 1, 2004 no longer support:
//       qprmGain
//       qprmOffset
//       qprmIntensifierGain
//
//       Please use the following:
//		 qprmNormalizedGain
//		 qprmS32AbsoluteOffset
//       qprm64NormIntensGain
//
// Note: Some parameters may not be supported on each camera.  Please check with QCam_IsParamSupported.
//       
typedef enum
{
	qprmGain						= 0,	// Deprecated
	qprmOffset						= 1,	// Deprecated
	qprmExposure					= 2,	// Exposure in microseconds
	qprmBinning						= 3,	// Symmetrical binning	(ex: 1x1 or 4x4)
	qprmHorizontalBinning			= 4,	// Horizonal binning	(ex: 2x1)
	qprmVerticalBinning				= 5,	// Vertical binning		(ex: 1x4)
	qprmReadoutSpeed				= 6,	// Readout speed (see QCam_qcReadoutSpeed)
	qprmTriggerType					= 7,	// Trigger type (see QCam_qcTriggerType)
	qprmColorWheel					= 8,	// Manual control of current RGB filter wheel color
	qprmCoolerActive				= 9,	// 1 turns cooler on, 0 turns off
	qprmExposureRed					= 10,	// For RGB filter mode, exposure (us) of red shot
	qprmExposureBlue				= 11,	// For RGB filter mode, exposure (us) of blue shot
	qprmImageFormat					= 12,	// Image format (see QCam_ImageFormat)
	qprmRoiX						= 13,	// Upper left X coordinate of the ROI
	qprmRoiY						= 14,	// Upper left Y coordinate of the ROI
	qprmRoiWidth					= 15,	// Width of ROI, in pixels
	qprmRoiHeight					= 16,	// Height of ROI, in pixels
	qprmReserved1					= 17,
	qprmShutterState				= 18,	// Shutter position
	qprmReserved2					= 19,
	qprmSyncb						= 20,	// Output type for SyncB port (see QCam_qcSyncb)
	qprmReserved3					= 21,
	qprmIntensifierGain				= 22,	// Deprecated
	qprmTriggerDelay				= 23,	// Trigger delay in nanoseconds
	qprmCameraMode					= 24,	// Camera mode (see QCam_Mode)
	qprmNormalizedGain				= 25,	// Normalized camera gain (micro units)
	qprmNormIntensGaindB			= 26,	// Normalized intensifier gain dB (micro units)
	qprmDoPostProcessing			= 27,   // Turns post processing on and off, 1 = On 0 = Off
	qprmPostProcessGainRed			= 28,	// Post processing red gain
	qprmPostProcessGainGreen		= 29,	// Post processing green gain
	qprmPostProcessGainBlue			= 30,	// Post processing blue gain
	qprmPostProcessBayerAlgorithm	= 31,	// Post processing bayer algorithm to use (see QCam_qcBayerInterp in QCamImgfnc.h)
	qprmPostProcessImageFormat		= 32,	// Post processing image format	
	qprmFan							= 33,	// Fan speed (see QCam_qcFanSpeed)
	qprmBlackoutMode				= 34,	// Blackout mode, 1 turns all lights off, 0 turns them back on
	qprmHighSensitivityMode			= 35,	// High sensitivity mode, 1 turns high sensitivity mode on, 0 turns it off
	qprmReadoutPort					= 36,	// The readout port (see QCam_qcReadoutPort)
	qprmEMGain						= 37,	// EM (Electron Multiplication) Gain 
	qprmOpenDelay					= 38,	// Open delay for the shutter.  Range is 0-419.43ms.  Must be smaller than expose time - 10us.  (micro units)
	qprmCloseDelay					= 39,	// Close delay for the shutter.  Range is 0-419.43ms.  Must be smaller than expose time - 10us.  (micro units)
	qprmCCDClearingMode				= 40,	// CCD clearing mode (see QCam_qcCCDClearingModes)
	qprmOverSample					= 41,	// set the oversample mode, only available on qcCameraGo21
	qprmReserved5					= 42,	
	qprmReserved6					= 43,	
	qprmReserved7					= 44,	
	qprmReserved4					= 45,	// QImaging OEM reserved parameter
	qprmReserved8					= 46,	// QImaging OEM reserved parameter
 	qprm_last						= 47,
	_qprm_force32					= 0xFFFFFFFF
}
QCam_Param;


// Camera Parameters - Signed 32 bit
//
// For use with QCam_GetParamS32, 
//				QCam_GetParamS32Min
//				QCam_GetParamS32Max
//				QCam_SetParamS32
//				QCam_GetParamSparseTableS32
//				QCam_IsSparseTableS32
//				QCam_IsRangeTableS32
//				QCam_IsParamS32Supported
//
typedef enum
{
	qprmS32NormalizedGaindB		= 0,	// Normalized camera gain in dB (micro units)
	qprmS32AbsoluteOffset		= 1,	// Absolute camera offset
	qprmS32RegulatedCoolingTemp = 2,	// Regulated cooling temperature (C)
	qprmS32_last				= 3,
	_qprmS32_force32			= 0xFFFFFFFF
}
QCam_ParamS32;


// Camera Parameters - Unsigned 64 bit
//
// For use with QCam_GetParam64, 
//				QCam_GetParam64Min
//				QCam_GetParam64Max
//				QCam_SetParam64
//				QCam_GetParamSparseTable64
//				QCam_IsSparseTable64
//				QCam_IsRangeTable64
//				QCam_IsParam64Supported
//
typedef enum
{
	qprm64Exposure			= 0,	// Exposure in nanoseconds
	qprm64ExposureRed		= 1,	// For RGB filter mode, exposure (nanoseconds) of red shot
	qprm64ExposureBlue		= 2,	// For RGB filter mode, exposure (nanoseconds) of blue shot
	qprm64NormIntensGain	= 3,	// Normalized intensifier gain (micro units)
 	qprm64_last				= 4,
	_qprm64_force32			= 0xFFFFFFFF
}
QCam_Param64;


// Camera Info Parameters
//
// For use with QCam_GetInfo
//
typedef enum
{
	qinfCameraType				= 0,	// Camera model (see QCam_qcCameraType)
	qinfSerialNumber			= 1,	// Deprecated
	qinfHardwareVersion			= 2,	// Hardware version
	qinfFirmwareVersion			= 3,	// Firmware version
	qinfCcd						= 4,	// CCD model (see QCam_qcCcd)
	qinfBitDepth				= 5,	// Maximum bit depth
	qinfCooled					= 6,	// Returns 1 if cooler is available, 0 if not
	qinfReserved1				= 7,	// Reserved
	qinfImageWidth				= 8,	// Width of the ROI (in pixels)
	qinfImageHeight				= 9,	// Height of the ROI (in pixels)
	qinfImageSize				= 10,	// Size of returned image (in bytes)
	qinfCcdType					= 11,	// CDD type (see QCam_qcCcdType)
	qinfCcdWidth				= 12,	// CCD maximum width
	qinfCcdHeight				= 13,	// CCD maximum height
	qinfFirmwareBuild			= 14,	// Build number of the firmware
	qinfUniqueId				= 15,	// Same as uniqueId in QCam_CamListItem
	qinfIsModelB				= 16,	// Cameras manufactured after March 1, 2004 return 1, otherwise 0
	qinfIntensifierModel		= 17,	// Intensifier tube model (see QCam_qcIntensifierModel)
	qinfExposureRes				= 18,	// Exposure time resolution (nanoseconds)
	qinfTriggerDelayRes			= 19, 	// Trigger delay Resolution (nanoseconds)
	qinfStreamVersion			= 20,	// Streaming version
	qinfNormGainSigFigs			= 21,	// Normalized Gain Significant Figures resolution
	qinfNormGaindBRes			= 22,	// Normalized Gain dB resolution (in micro units)
	qinfNormITGainSigFigs		= 23,	// Normalized Intensifier Gain Significant Figures
	qinfNormITGaindBRes			= 24,	// Normalized Intensifier Gain dB resolution (micro units)
	qinfRegulatedCooling		= 25,	// 1 if camera has regulated cooling
	qinfRegulatedCoolingLock	= 26,	// 1 if camera is at regulated temperature, 0 otherwise
	qinfFanControl				= 29,	// 1 if camera can control fan speed
	qinfHighSensitivityMode		= 30,	// 1 if camera has high sensitivity mode available
	qinfBlackoutMode			= 31,	// 1 if camera has blackout mode available
	qinfPostProcessImageSize	= 32,	// Returns the size (in bytes) of the post-processed image
	qinfAsymmetricalBinning		= 33,	// 1 if camera has asymmetrical binning (ex: 2x4)
	qinfEMGain					= 34,	// 1 if EM gain is supported, 0 if not
	qinfOpenDelay				= 35,	// 1 if shutter open delay controls are available, 0 if not
	qinfCloseDelay				= 36,	// 1 if shutter close delay controls are available, 0 if not
	qinfColorWheelSupported		= 37,	// 1 if color wheel is supported, 0 if not	
	qinfReserved2				= 38,	
	qinfReserved3				= 39,	
	qinfReserved4				= 40,	
	qinfReserved5				= 41,
	qinf_last					= 42,
	_qinf_force32				= 0xFFFFFFFF
}
QCam_Info;


// Error Codes
//
typedef enum
{
	qerrSuccess				= 0,		
	qerrNotSupported		= 1,	// Function is not supported for this device
	qerrInvalidValue		= 2,	// A parameter used was invalid
	qerrBadSettings			= 3,	// The QCam_Settings structure is corrupted
	qerrNoUserDriver		= 4,
	qerrNoFirewireDriver	= 5,	// Firewire device driver is missing
	qerrDriverConnection	= 6,
	qerrDriverAlreadyLoaded	= 7,	// The driver has already been loaded
	qerrDriverNotLoaded		= 8,	// The driver has not been loaded.
	qerrInvalidHandle		= 9,	// The QCam_Handle has been corrupted
	qerrUnknownCamera		= 10,	// Camera model is unknown to this version of QCam
	qerrInvalidCameraId		= 11,	// Camera id used in QCam_OpenCamera is invalid
	qerrNoMoreConnections	= 12,	// Deprecated
	qerrHardwareFault		= 13,
	qerrFirewireFault		= 14,
	qerrCameraFault			= 15,
	qerrDriverFault			= 16,
	qerrInvalidFrameIndex	= 17,
	qerrBufferTooSmall		= 18,	// Frame buffer (pBuffer) is too small for image
	qerrOutOfMemory			= 19,
	qerrOutOfSharedMemory	= 20,
	qerrBusy				= 21,	// The function used cannot be processed at this time
	qerrQueueFull			= 22,	// The queue for frame and settings changes is full
	qerrCancelled			= 23,
	qerrNotStreaming		= 24,	// The function used requires that streaming be on
	qerrLostSync			= 25,	// The host and the computer are out of sync, the frame returned is invalid
	qerrBlackFill			= 26,	// Data is missing in the frame returned
	qerrFirewireOverflow	= 27,	// The host has more data than it can process, restart streaming.
	qerrUnplugged			= 28,	// The camera has been unplugged or turned off
	qerrAccessDenied		= 29,	// The camera is already open
	qerrStreamFault			= 30,	// Stream allocation failed, there may not be enough bandwidth
	qerrQCamUpdateNeeded	= 31,	// QCam needs to be updated
	qerrRoiTooSmall			= 32,	// The ROI used is too small
	qerr_last				= 33,
	_qerr_force32			= 0xFFFFFFFF
}
QCam_Err;


#pragma mark STRUCTURES

typedef void* QCam_Handle;


typedef struct
{
	unsigned long size;						// Deprecated, no longer necessary.
	unsigned long _private_data[ 64 ];
}
QCam_Settings;



typedef struct
{
	unsigned long		cameraId;			// Camera ID (ex: 0 for first camera, 1 for second)
	unsigned long		cameraType;			// Camera Model
	unsigned long		uniqueId;			// Unique ID for the camera
	unsigned long		isOpen;				// 1 if already open, 0 if closed

	unsigned long		_reserved[ 10 ];
}
QCam_CamListItem;


//
// Note: Any functions that accept a QCam_Frame as a parameter
// must have the IN fields filled in before making the call.
// (ex: pBuffer must be allocated before passing a QCam_Frame to QCam_QueueFrame)
//
// Note: The fields designated with the OUT tag are set by calls that
// return a QCam_Frame.
//
typedef struct
{
	void*			pBuffer;			// Image buffer, 4-byte aligned				IN / OUT
	unsigned long		bufferSize;			// Length of the buffer (pBuffer), in bytes		IN

	unsigned long		format;				// Format of image					OUT
	unsigned long		width;				// Image width, in pixels				OUT
	unsigned long		height;				// Image height, in pixels				OUT
	unsigned long		size;				// Size of image data, in bytes				OUT
	unsigned short		bits;				// Bit depth						OUT
	unsigned short		frameNumber;			// Rolling frame number					OUT
	unsigned long		bayerPattern;			// For bayer CCDs, the mosaic pattern			OUT
	unsigned long		errorCode;			// Error code for the frame (see QCam_Err)		OUT
	unsigned long		timeStamp;			// Exposure time stamp					OUT

	unsigned long		_reserved[ 8 ];
}
QCam_Frame;


// Callback for QCam_QueueFrame and QCam_QueueSettings
//
typedef void ( QCAMAPI *QCam_AsyncCallback )
(
	void*				userPtr,			// User defined
	unsigned long		userData,			// User defined
	QCam_Err			errcode,			// Error code
	unsigned long		flags				// Combination of flags (see QCam_qcCallbackFlags)
);


#pragma mark FUNCTIONS

// Please see the QCam API.pdf for more information on each function


/*
 *  QCam_LoadDriver()
 *  
 *  Discussion:
 *    Initializes QCam.  This call must be made before using any other QCam functions.
 *  
 *  Parameters:
 *    None
 *  
 *	Remarks:
 *	  None
 *  
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_LoadDriver
(
	void
);


/*
 *  QCam_ReleaseDriver()
 *  
 *  Discussion:
 *    Shutdown QCam.
 *  
 *  Parameters:
 *    None
 *	
 *	Remarks:
 *	  None
 *  
 *  Result:
 *    None
 */
extern void QCAMAPI QCam_ReleaseDriver
(
	void
);


/*
 *  QCam_LibVersion()
 *  
 *  Discussion:
 *    Returns the version of QCam.
 *  
 *  Parameters:
 *	(OUT)	verMajor - Major version
 *	(OUT)	verMinor - Minor version
 *	(OUT)	verBuild - Build version
 *	
 *	Remarks: 
 *	  The version number uses the following scheme: verMajor.verMinor.verBuild
 *    (ex: 1.9.0)
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_LibVersion
(
	unsigned short*		verMajor,
	unsigned short*		verMinor,
	unsigned short*		verBuild
);


/*
 *  QCam_Version()
 *  
 *  Discussion:
 *    Returns the version of QCam.
 *  
 *  Parameters:
 *	(OUT)	verMajor - Major version
 *	(OUT)	verMinor - Minor version
 *	
 *	Remarks: 
 *	  The version number uses the following scheme: verMajor.verMinor
 *    (ex: 1.9)
 *	  Note: To find out more detailed information, please use QCam_LibVersion
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_Version
(
	unsigned short*		verMajor,
	unsigned short*		verMinor
);


/*
 *  QCam_ListCameras()
 *  
 *  Discussion:
 *    Retrieve a list of connected cameras.
 *  
 *  Parameters:
 *	(IN)	pList - User allocated array to fill in
 *	(OUT)	pList - Filled in with the list of connected cameras
 *	(IN)	pNumberInList - Length of the array
 *	(OUT)	pNumberInList - Number of cameras found
 *	
 *	Remarks: 
 *	  On return, pNumberInList may contain a number that is bigger than the array size.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_ListCameras
(
	QCam_CamListItem*	pList,				
	unsigned long*		pNumberInList		
);


/*
 *  QCam_OpenCamera()
 *  
 *  Discussion:
 *    Open a connection to the camera.
 *  
 *  Parameters:
 *	(IN)	cameraId - The id of the camera to open
 *	(OUT)	handle - Camera handle to use with functions that require a QCam_Handle
 *	
 *	Remarks: 
 *	  The camera id is from the cameraId field of the QCam_CamListItem structure.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_OpenCamera
(
	unsigned long		cameraId,			
	QCam_Handle*		pHandle				
);


/*
 *  QCam_CloseCamera()
 *  
 *  Discussion:
 *    Closes the connection to a camera.
 *  
 *  Parameters:
 *	(IN)	handle - Camera handle
 *	
 *	Remarks: 
 *	  None
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_CloseCamera
(
	QCam_Handle			handle				
);


/*
 *  QCam_RegisterUnpluggedCallback()
 *  
 *  Discussion:
 *    Register a callback to be called if the camera is surprisingly removed
 *  
 *  Parameters:
 *	(IN)	handle - Handle to the camera
 *  (IN)	callback - The callback to use
 *	(IN)	userPtr - Pointer that will be passed in to the callback when it is called
 *	
 *	Remarks: 
 *	  Callback may not be null.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_RegisterUnpluggedCallback
(
	QCam_Handle			handle,			
	QCam_AsyncCallback	callback,			
	void*				usrPtr				
);


/*
 *  QCam_GetSerialString()
 *  
 *  Discussion:
 *    Returns the serial number of the camera.
 *  
 *  Parameters:
 *	(IN)	handle - Handle to the camera
 *  (IN)	string - String buffer to use
 *  (OUT)	string - The serial number
 *	(IN)	size - Size of the string buffer
 *	
 *	Remarks: 
 *	  This function is supported on cameras produced after Mar 1, 2004.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_GetSerialString
(
	QCam_Handle			handle,				
	char*				string,				
	unsigned long		size				
);


/*
 *  QCam_GetCameraModelString()
 *  
 *  Discussion:
 *    Returns the model of the camera as a string.
 *    Example: "Retiga SRV"
 *  
 *  Parameters:
 *	(IN)	handle - Handle to the camera
 *  (IN)	string - String buffer to use
 *  (OUT)	string - The camera model as a string
 *	(IN)	size - Size of the string buffer
 *	
 *	Remarks: 
 *	  Will return "Unknown" if the camera requires a newer version of the driver.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_GetCameraModelString
(
	QCam_Handle			handle,				
	char*				string,				
	unsigned long		size				
);


/*
 *  QCam_GetInfo()
 *  
 *  Discussion:
 *    Returns information about the camera based on the parameter used.
 *  
 *  Parameters:
 *	(IN)	handle - Handle to the camera
 *  (IN)	infoKey - Get information about this parameter
 *  (OUT)	pValue - Value of the information
 *	
 *	Remarks: 
 *	  None
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_GetInfo
(
	QCam_Handle			handle,				
	QCam_Info			infoKey,			
	unsigned long*		pValue				
);


/*
 *  QCam_ReadDefaultSettings()
 *  
 *  Discussion:
 *    Returns the default camera settings.
 *  
 *  Parameters:
 *	(IN)	handle - Handle to the camera
 *  (OUT)	pSettings - Opaque settings structure
 *	
 *	Remarks: 
 *	  The QCam_Settings struct is an opaque structure.  Access the structure
 *    with QCam_GetParam() and QCam_SetParam() series of functions.  The QCam_Settings struct 
 *    can be saved or restored from a file, and is forward and backward compatible
 *    with different QCam versions.
 *
 *    A QCam_Settings structure must be initalized by calling either
 *    QCam_ReadDefaultSettings() or QCam_ReadSettingsFromCam().
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_ReadDefaultSettings
(
	QCam_Handle			handle,				
	QCam_Settings*		pSettings
);


/*
 *  QCam_ReadSettingsFromCam()
 *  
 *  Discussion:
 *    Returns the camera settings.
 *  
 *  Parameters:
 *	(IN)	handle - Handle to the camera
 *  (OUT)	pSettings - Opaque settings structure
 *	
 *	Remarks: 
 *	  This function differs from QCam_ReadDefaultSettings() because this
 *
 *    returns the settings that are in the camera, and not the default ones.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_ReadSettingsFromCam
(
	QCam_Handle			handle,			
	QCam_Settings*		pSettings
);


/*
 *  QCam_SendSettingsToCam()
 *  
 *  Discussion:
 *    Send the settings to the camera.
 *  
 *  Parameters:
 *	(IN)	handle - Handle to the camera
 *  (IN)	pSettings - Opaque settings structure
 *	
 *	Remarks: 
 *	  Sets the camera based on the info in the settings structure.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_SendSettingsToCam
(
	QCam_Handle			handle,
	QCam_Settings*		pSettings
);


/*
 *  QCam_PreflightSettings()
 *  
 *  Discussion:
 *    Changes your settings struct just as with QCam_SendSettingsToCam(),
 *    without sending anything to the camera.
 *  
 *  Parameters:
 *	(IN)	handle - Handle to the camera
 *  (IN)	pSettings - Opaque settings structure
 *	
 *	Remarks: 
 *	  None.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_PreflightSettings
(
	QCam_Handle			handle,				
	QCam_Settings*		pSettings			
);


/*
 *  QCam_TranslateSettings()
 *  
 *  Discussion:
 *    Translates a settings structure so another camera can use it.
 *  
 *  Parameters:
 *	(IN)	handle - Handle to the camera
 *  (IN)	pSettings - Opaque settings structure
 *	
 *	Remarks: 
 *	  Deprecated.  No longer used.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_TranslateSettings
(
	QCam_Handle			handle,				
	QCam_Settings*		pSettings													
);


/*
 *  QCam_GetParam()
 *  
 *  Discussion:
 *    Returns the value of a parameter.
 *  
 *  Parameters:
 *  (IN)	pSettings - Opaque settings structure to retreive the value from
 *  (IN)	paramKey - The parameter to look up
 *  (OUT)	pValue - The parameter value
 *	
 *	Remarks: 
 *	  Returns an unsigned 32 bit value from a QCam_Param parameter.
 *
 *    The settings structure must have been initialized prior to calling this function.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_GetParam
(
	QCam_Settings const* pSettings,			
	QCam_Param			paramKey,			
	unsigned long*		pValue				
);


/*
 *  QCam_GetParamS32()
 *  
 *  Discussion:
 *    Returns the value of a parameter.
 *  
 *  Parameters:
 *  (IN)	pSettings - Opaque settings structure to retreive the value from
 *  (IN)	paramKey - The parameter to look up
 *  (OUT)	pValue - The parameter value
 *	
 *	Remarks: 
 *	  Returns a signed 32 bit value from a QCam_ParamS32 parameter.
 *
 *    The settings structure must have been initialized prior to calling this function.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_GetParamS32
(
	QCam_Settings const* pSettings,			
	QCam_ParamS32		paramKey,			
	signed long*		pValue				
);


/*
 *  QCam_GetParam64()
 *  
 *  Discussion:
 *    Returns the value of a parameter.
 *  
 *  Parameters:
 *  (IN)	pSettings - Opaque settings structure to retreive the value from
 *  (IN)	paramKey - The parameter to look up
 *  (OUT)	pValue - The parameter value
 *	
 *	Remarks: 
 *	  Returns an unsigned 64 bit value from a QCam_Param64 parameter.
 *
 *    The settings structure must have been initialized prior to calling this function.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_GetParam64
(
	QCam_Settings const* pSettings,			
	QCam_Param64 		paramKey,			
	UNSIGNED64*			pValue				
);


/*
 *  QCam_SetParam()
 *  
 *  Discussion:
 *    Sets the value of a parameter.
 *  
 *  Parameters:
 *  (IN)	pSettings - Opaque settings structure to use
 *  (IN)	paramKey - The parameter to set
 *  (OUT)	pValue - The parameter value
 *	
 *	Remarks: 
 *	  Sets an unsigned 32 bit value for the QCam_Param parameter.
 *
 *    The settings structure must have been initialized prior to calling this function.
 *
 *    The function QCam_SendSettingsToCam() needs to be called to then set the values on the camera.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_SetParam
(
	QCam_Settings*		pSettings,			
	QCam_Param			paramKey,			
	unsigned long		value				
);


/*
 *  QCam_SetParamS32()
 *  
 *  Discussion:
 *    Sets the value of a parameter.
 *  
 *  Parameters:
 *  (IN)	pSettings - Opaque settings structure to use
 *  (IN)	paramKey - The parameter to set
 *  (OUT)	pValue - The parameter value
 *	
 *	Remarks: 
 *	  Sets a signed 32 bit value for the QCam_ParamS32 parameter.
 *
 *    The settings structure must have been initialized prior to calling this function.
 *
 *    The function QCam_SendSettingsToCam() needs to be called to then set the values on the camera.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_SetParamS32
(
	QCam_Settings*		pSettings,			
	QCam_ParamS32		paramKey,			
	signed long			value				
);


/*
 *  QCam_SetParam64()
 *  
 *  Discussion:
 *    Sets the value of a parameter.
 *  
 *  Parameters:
 *  (IN)	pSettings - Opaque settings structure to use
 *  (IN)	paramKey - The parameter to set
 *  (OUT)	pValue - The parameter value
 *	
 *	Remarks: 
 *	  Sets an unsigned 64 bit value for the QCam_Param64 parameter.
 *
 *    The settings structure must have been initialized prior to calling this function.
 *
 *    The function QCam_SendSettingsToCam() needs to be called to then set the values on the camera.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_SetParam64
(
	QCam_Settings*		pSettings,			
	QCam_Param64		paramKey,			
	UNSIGNED64			value				
);


/*
 *  QCam_GetParamMin()
 *  
 *  Discussion:
 *    Returns the minimum value for a parameter.
 *  
 *  Parameters:
 *  (IN)	pSettings - Opaque settings structure to retreive the value from
 *  (IN)	paramKey - The parameter to look up
 *  (OUT)	pValue - The parameter value
 *	
 *	Remarks: 
 *	  Returns the mimimum of an unsigned 32 bit value from a QCam_Param parameter.
 *
 *    The settings structure must have been initialized prior to calling this function.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_GetParamMin
(
	QCam_Settings const*	pSettings,		
	QCam_Param				paramKey,		
	unsigned long*			pValue			
);


/*
 *  QCam_GetParamS32Min()
 *  
 *  Discussion:
 *    Returns the minimum value for a parameter.
 *  
 *  Parameters:
 *  (IN)	pSettings - Opaque settings structure to retreive the value from
 *  (IN)	paramKey - The parameter to look up
 *  (OUT)	pValue - The parameter value
 *	
 *	Remarks: 
 *	  Returns the mimimum of a signed 32 bit value from a QCam_ParamS32 parameter.
 *
 *    The settings structure must have been initialized prior to calling this function.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_GetParamS32Min
(
	QCam_Settings const*	pSettings,		
	QCam_ParamS32			paramKey,		
	signed long*			pValue		
);


/*
 *  QCam_GetParam64Min()
 *  
 *  Discussion:
 *    Returns the minimum value for a parameter.
 *  
 *  Parameters:
 *  (IN)	pSettings - Opaque settings structure to retreive the value from
 *  (IN)	paramKey - The parameter to look up
 *  (OUT)	pValue - The parameter value
 *	
 *	Remarks: 
 *	  Returns the mimimum of an unsigned 64 bit value from a QCam_Param64 parameter.
 *
 *    The settings structure must have been initialized prior to calling this function.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_GetParam64Min
(
	QCam_Settings const*	pSettings,		
	QCam_Param64			paramKey,		
	UNSIGNED64*				pValue			
);


/*
 *  QCam_GetParamMax()
 *  
 *  Discussion:
 *    Returns the maximum value for a parameter.
 *  
 *  Parameters:
 *  (IN)	pSettings - Opaque settings structure to retreive the value from
 *  (IN)	paramKey - The parameter to look up
 *  (OUT)	pValue - The parameter value
 *	
 *	Remarks: 
 *	  Returns the maximum of an unsigned 32 bit value from a QCam_Param parameter.
 *
 *    The settings structure must have been initialized prior to calling this function.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_GetParamMax
(
	QCam_Settings const*	pSettings,		
	QCam_Param				paramKey,		
	unsigned long*			pValue			
);


/*
 *  QCam_GetParamS32Max()
 *  
 *  Discussion:
 *    Returns the maximum value for a parameter.
 *  
 *  Parameters:
 *  (IN)	pSettings - Opaque settings structure to retreive the value from
 *  (IN)	paramKey - The parameter to look up
 *  (OUT)	pValue - The parameter value
 *	
 *	Remarks: 
 *	  Returns the maximum of a signed 32 bit value from a QCam_ParamS32 parameter.
 *
 *    The settings structure must have been initialized prior to calling this function.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_GetParamS32Max
(
	QCam_Settings const*	pSettings,		
	QCam_ParamS32			paramKey,		
	signed long*			pValue			
);


/*
 *  QCam_GetParam64Max()
 *  
 *  Discussion:
 *    Returns the maximum value for a parameter.
 *  
 *  Parameters:
 *  (IN)	pSettings - Opaque settings structure to retreive the value from
 *  (IN)	paramKey - The parameter to look up
 *  (OUT)	pValue - The parameter value
 *	
 *	Remarks: 
 *	  Returns the maximum of an unsigned 64 bit value from a QCam_Param64 parameter.
 *
 *    The settings structure must have been initialized prior to calling this function.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_GetParam64Max
(
	QCam_Settings const*	pSettings,		
	QCam_Param64			paramKey,		
	UNSIGNED64*				pValue			
);


/*
 *  QCam_GetParamSparseTable()
 *  
 *  Discussion:
 *    Returns a sparse table for a parameter.
 *  
 *  Parameters:
 *  (IN)	pSettings - Opaque settings structure to retreive the sparse table from
 *  (IN)	paramKey - The parameter to look up
 *  (OUT)	pSparseTable - The returned sparse table
 *  (IN)	uSize - The size of the sparse table
 *  (OUT)	uSize - Number of entries
 *	
 *	Remarks: 
 *	  Returns the sprase table with unsigned 32 bit values from a QCam_Param parameter.
 *
 *    The settings structure must have been initialized prior to calling this function.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_GetParamSparseTable
(
	QCam_Settings const*	pSettings,		
	QCam_Param				paramKey,		
	unsigned long*			pSparseTable,	
	int*					uSize			
);


/*
 *  QCam_GetParamSparseTableS32()
 *  
 *  Discussion:
 *    Returns a sparse table for a parameter.
 *  
 *  Parameters:
 *  (IN)	pSettings - Opaque settings structure to retreive the sparse table from
 *  (IN)	paramKey - The parameter to look up
 *  (OUT)	pSparseTable - The returned sparse table
 *  (IN)	uSize - The size of the sparse table
 *  (OUT)	uSize - Number of entries
 *	
 *	Remarks: 
 *	  Returns the sprase table with signed 32 bit values from a QCam_ParamS32 parameter.
 *
 *    The settings structure must have been initialized prior to calling this function.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_GetParamSparseTableS32
(
	QCam_Settings const*	pSettings,		
	QCam_ParamS32			paramKey,		
	signed long*			pSparseTable,	
	int*					uSize			
);


/*
 *  QCam_GetParamSparseTable64()
 *  
 *  Discussion:
 *    Returns a sparse table for a parameter.
 *  
 *  Parameters:
 *  (IN)	pSettings - Opaque settings structure to retreive the sparse table from
 *  (IN)	paramKey - The parameter to look up
 *  (OUT)	pSparseTable - The returned sparse table
 *  (IN)	uSize - The size of the sparse table
 *  (OUT)	uSize - Number of entries
 *	
 *	Remarks: 
 *	  Returns the sprase table with unsigned 64 bit values from a QCam_Param64 parameter.
 *
 *    The settings structure must have been initialized prior to calling this function.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_GetParamSparseTable64
(
	QCam_Settings const*	pSettings,		
	QCam_Param64			paramKey,		
	UNSIGNED64*				pSparseTable,	
	int*					uSize		
);


/*
 *  QCam_IsSparseTable()
 *  
 *  Discussion:
 *    Returns qerrSuccess if the parameter is a sparse table, and qerrNotSupported otherwise.
 *  
 *  Parameters:
 *  (IN)	pSettings - Opaque settings structure to retreive the value from
 *  (IN)	paramKey - The parameter to check
 *	
 *	Remarks: 
 *	  For use with QCam_Param parameters.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_IsSparseTable
(
	QCam_Settings const*	pSettings,		
	QCam_Param				paramKey	
);


/*
 *  QCam_IsSparseTableS32()
 *  
 *  Discussion:
 *    Returns qerrSuccess if the parameter is a sparse table, and qerrNotSupported otherwise.
 *  
 *  Parameters:
 *  (IN)	pSettings - Opaque settings structure to retreive the value from
 *  (IN)	paramKey - The parameter to check
 *	
 *	Remarks: 
 *	  For use with QCam_ParamS32 parameters.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_IsSparseTableS32
(
	QCam_Settings const*	pSettings,		
	QCam_ParamS32			paramKey		
);


/*
 *  QCam_IsSparseTable64()
 *  
 *  Discussion:
 *    Returns qerrSuccess if the parameter is a sparse table, and qerrNotSupported otherwise.
 *  
 *  Parameters:
 *  (IN)	pSettings - Opaque settings structure to retreive the value from
 *  (IN)	paramKey - The parameter to check
 *	
 *	Remarks: 
 *	  For use with QCam_Param64 parameters.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_IsSparseTable64
(
	QCam_Settings const*	pSettings,		
	QCam_Param64			paramKey		
);


/*
 *  QCam_IsRangeTable()
 *  
 *  Discussion:
 *    Returns qerrSuccess if the parameter is a range table, and qerrNotSupported otherwise.
 *  
 *  Parameters:
 *  (IN)	pSettings - Opaque settings structure to retreive the value from
 *  (IN)	paramKey - The parameter to check
 *	
 *	Remarks: 
 *	  For use with QCam_Param parameters.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_IsRangeTable
(
	QCam_Settings const*	pSettings,		
	QCam_Param				paramKey		
);


/*
 *  QCam_IsRangeTableS32()
 *  
 *  Discussion:
 *    Returns qerrSuccess if the parameter is a range table, and qerrNotSupported otherwise.
 *  
 *  Parameters:
 *  (IN)	pSettings - Opaque settings structure to retreive the value from
 *  (IN)	paramKey - The parameter to check
 *	
 *	Remarks: 
 *	  For use with QCam_ParamS32 parameters.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_IsRangeTableS32
(
	QCam_Settings const*	pSettings,		
	QCam_ParamS32			paramKey		
);


/*
 *  QCam_IsRangeTable64()
 *  
 *  Discussion:
 *    Returns qerrSuccess if the parameter is a range table, and qerrNotSupported otherwise.
 *  
 *  Parameters:
 *  (IN)	pSettings - Opaque settings structure to retreive the value from
 *  (IN)	paramKey - The parameter to check
 *	
 *	Remarks: 
 *	  For use with QCam_Param64 parameters.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_IsRangeTable64
(
	QCam_Settings const*	pSettings,	
	QCam_Param64			paramKey
);


/*
 *  QCam_IsParamSupported()
 *  
 *  Discussion:
 *    Returns qerrSuccess if the parameter is supported on a particular camera, and qerrNotSupported if not.
 *  
 *  Parameters:
 *  (IN)	handle - Handle to the camera to check it with
 *  (IN)	paramKey - The parameter to check
 *	
 *	Remarks: 
 *	  For use with QCam_Param parameters.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_IsParamSupported
(
	QCam_Handle			handle,				
	QCam_Param			paramKey			
);


/*
 *  QCam_IsParamS32Supported()
 *  
 *  Discussion:
 *    Returns qerrSuccess if the parameter is supported on a particular camera, and qerrNotSupported if not.
 *  
 *  Parameters:
 *  (IN)	handle - Handle to the camera to check it with
 *  (IN)	paramKey - The parameter to check
 *	
 *	Remarks: 
 *	  For use with QCam_ParamS32 parameters.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_IsParamS32Supported
(
	QCam_Handle			handle,				
	QCam_ParamS32		paramKey			
);


/*
 *  QCam_IsParam64Supported()
 *  
 *  Discussion:
 *    Returns qerrSuccess if the parameter is supported on a particular camera, and qerrNotSupported if not.
 *  
 *  Parameters:
 *  (IN)	handle - Handle to the camera to check it with
 *  (IN)	paramKey - The parameter to check
 *	
 *	Remarks: 
 *	  For use with QCam_Param64 parameters.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_IsParam64Supported
(
	QCam_Handle			handle,				
	QCam_Param64		paramKey		
);


/*
 *  QCam_SetStreaming()
 *  
 *  Discussion:
 *    Enable / disable streaming of images
 *  
 *  Parameters:
 *  (IN)	handle - Handle to the camera
 *  (IN)	enable - 0 to disable, 1 to enable
 *	
 *	Remarks: 
 *	  None
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_SetStreaming
(
	QCam_Handle			handle,				
	unsigned long		enable				
);


/*
 *  QCam_Trigger()
 *  
 *  Discussion:
 *    Trigger the start of an exposure
 *  
 *  Parameters:
 *  (IN)	handle - Handle to the camera
 *	
 *	Remarks: 
 *	  This call is designed to work with cameras manufactured after March 1, 2004.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_Trigger
(
	QCam_Handle			handle				
);


/*
 *  QCam_Abort()
 *  
 *  Discussion:
 *    Stop all frames and settings that have been queued up.
 *  
 *  Parameters:
 *  (IN)	handle - Handle to the camera
 *	
 *	Remarks: 
 *	  This call will remove all elements from the internal queue. 
 *
 *    Any frames or settings that have been queued up with
 *    QCam_QueueFrame() or QCam_QueueSettings() will not fire
 *    their callbacks.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_Abort
(
	QCam_Handle			handle				
);


/*
 *  QCam_GrabFrame()
 *  
 *  Discussion:
 *    Synchronously capture one frame.
 *  
 *  Parameters:
 *  (IN)	handle - Handle to the camera
 *  (OUT)	pFrame - Captured frame
 *	
 *	Remarks: 
 *	  The buffer for the frame must be allocated by the user before
 *    calling this function.
 *
 *    This function will block until the frame has been captured.
 *
 *    A faster frame rate can be achieved by turning streaming on
 *    before calling this function.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_GrabFrame
(
	QCam_Handle			handle,				
	QCam_Frame*			pFrame			
);


/*
 *  QCam_QueueFrame()
 *  
 *  Discussion:
 *    Asynchronously capture one frame.
 *  
 *  Parameters:
 *  (IN)	handle - Handle to the camera
 *  (IN)	pFrame - Frame to use
 *  (IN)	callback - The completion callback to use.  Can be null.
 *  (IN)	cbFlags - Specifies when callback should be fired.
 *  (IN)	userPtr - User specified pointer that gets passed into the callback
 *  (IN)	userData - User specified data that gets passed into the callback
 *	
 *	Remarks: 
 *    The callback will be called one the frame has been captured.
 *
 *	  The buffer for the frame must be allocated by the user before
 *    calling this function.  The frame must persists until the frame
 *    is returned in the callback.
 *
 *    This function will return immediately.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_QueueFrame
(
	QCam_Handle			handle,				
	QCam_Frame*			pFrame,				
	QCam_AsyncCallback	callback,			
	unsigned long		cbFlags,			
	void*				userPtr,			
	unsigned long		userData			
);


/*
 *  QCam_QueueSettings()
 *  
 *  Discussion:
 *    Queue up a settings change.
 *  
 *  Parameters:
 *  (IN)	handle - Handle to the camera
 *  (IN)	pFrame - Settings structure to send
 *  (IN)	callback - The completion callback to use.  Can be null.
 *  (IN)	cbFlags - Specifies when callback should be fired.
 *  (IN)	userPtr - User specified pointer that gets passed into the callback
 *  (IN)	userData - User specified data that gets passed into the callback
 *	
 *	Remarks: 
 *    The callback will be called when the settings have been
 *    sent to the camera.
 *
 *	  The settings structure must persists until the settings
 *    have been sent.
 *
 *    This function will return immediately.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_QueueSettings
(
	QCam_Handle			handle,				
	QCam_Settings*		pSettings,			
	QCam_AsyncCallback	callback,		
	unsigned long		cbFlags,			
	void*				userPtr,		
	unsigned long		userData			
);


/*
 *  QCam_AutoExpose()
 *  
 *  Discussion:
 *    Run auto expose algorithm.
 *  
 *  Parameters:
 *  (IN)	pOpaque - Opaque settings structure to use
 *  (IN)	xOrig - The upper left hand x coordinate of the ROI used
 *  (IN)	yOrig - The upper left hand y coordinate of the ROI used 
 *  (IN)	width - The width of the ROI used
 *  (IN)	height - The height of the ROI used
 *	
 *	Remarks: 
 *	  The algorithm will attempt to capture up to six frames
 *    to set the exposure.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_AutoExpose
(
	QCam_Settings*			pOpaque,
	unsigned long			xOrig,
	unsigned long			yOrig,
	unsigned long			width,
	unsigned long			height
);


/*
 *  QCam_WhiteBalance()
 *  
 *  Discussion:
 *    Run auto white balance algorithm.
 *  
 *  Parameters:
 *  (IN)	pOpaque - Opaque settings structure to use
 *  (IN)	xOrig - The upper left hand x coordinate of the ROI used
 *  (IN)	yOrig - The upper left hand y coordinate of the ROI used 
 *  (IN)	width - The width of the ROI used
 *  (IN)	height - The height of the ROI used
 *	
 *	Remarks: 
 *	  The algorithm will attempt to capture up to six frames for the algorithm.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_WhiteBalance
(
	QCam_Settings*			pOpaque,
	unsigned long			xOrig,
	unsigned long			yOrig,
	unsigned long			width,
	unsigned long			height
);


/*
 *  QCam_PostProcessSingleFrame()
 *  
 *  Discussion:
 *    Post process a single frame.
 *  
 *  Parameters:
 *  (IN)	inHandle - Camera handle
 *  (IN)	inSettings - The settings structure to use
 *  (IN)	inFrame - The original un-processed frame
 *  (OUT)	outFrame - The post processed frame
 *	
 *	Remarks: 
 *	  qprmPostProcessImageFormat and qprmPostProcessBayerAlgorithm must
 *    be set before using this function.
 *
 *  Result:
 *    QCam_Err code
 */
extern QCam_Err QCAMAPI QCam_PostProcessSingleFrame
(
	QCam_Handle			inHandle, 
	QCam_Settings		*inSettings, 
	QCam_Frame			*inFrame,
	QCam_Frame			*outFrame
);



#ifdef __cplusplus
} // end extern "C"
#endif

#endif // QCAMAPI_H_INCLUDE
