/*
|==============================================================================
| Copyright (C) 2000 Quantitative Imaging Corporation.  All Rights Reserved.
| Reproduction or disclosure of this file or its contents without the prior
| written consent of Quantitative Imaging Corporation is prohibited.
|==============================================================================
|
| File:			QCamImgfnc.h
|
| Project/lib:	
|
| Target:		
|
| Description:	
|
| Notes:		
|
|==============================================================================
| dd/mon/yy  Author		Notes
|------------------------------------------------------------------------------
| 29/Nov/00  DavidL		Original.
| 31/Jan/01  DavidL		Version 1.00.
| 05/Sep/03  ChrisS		Added API call "QCam_BayerZoomVert".
| 22/09/04	 MattA		Added enum for qcBayerBiCubic
|==============================================================================
*/

#ifndef QCAMIMGFNC_H_INCLUDE
#define QCAMIMGFNC_H_INCLUDE

#ifdef __cplusplus
extern "C" {
#endif

//===== INCLUDE FILES =========================================================

#ifdef __APPLE_CC__
	#include <QCam/QCamApi.h>
#else
	#include <QCamApi.h>
#endif

//===== #DEFINES ==============================================================

//===== TYPE DEFINITIONS ======================================================

typedef enum
{
	qcBayerInterpNone,
	qcBayerInterpAvg4,						// Avg 4 for B,R; Avg 2 for G
	qcBayerInterpFast,						// Nearest neighbour
	qcBayerBiCubic,							// Bicubic
	qcBayerBiCubic_Faster,					// Bicubic without FP
	qcBayerInterp_last
}
QCam_qcBayerInterp;

//===== FUNCTION PROTOTYPES ===================================================

// Is this image format 8 bits (byte) or 16 bits (word)?
bool QCAMAPI QCam_is16bit( unsigned long format );

// Is this image format a 3 color (i.e. color but not bayer) format?
bool QCAMAPI QCam_is3Color( unsigned long format );

// Is this image format a bayer format?
bool QCAMAPI QCam_isBayer( unsigned long format );

// Is this image format a color format (bayer, or 3-color lcd)?
bool QCAMAPI QCam_isColor( unsigned long format );

// Is this image format monochrome (qfmtMono8, qfmtMono16)?
bool QCAMAPI QCam_isMonochrome( unsigned long format );

// Calculate the image size, in bytes.
unsigned long QCAMAPI QCam_CalcImageSize( unsigned long format,
										  unsigned long width,
										  unsigned long height );

//
// Interpolate the Bayer ccd pattern.
//
// Parameters:
//
//		algorithm - interpolation method to use
//
//		pFrameIn  - a frame from QCam
//
//		pFrameOut - you must fill in the following fields:
//						pBuffer      an allocated buffer to hold output image
//						bufferSize   size of the buffer in bytes
//						format       the desired color output format (must be
//										the same bit depth as the input format)
//
void QCAMAPI QCam_BayerToRgb( QCam_qcBayerInterp algorithm,
							  QCam_Frame* pFrameIn, QCam_Frame* pFrameOut );


//
// Expand a Bayer pattern in the vertical direction by a multiple of 2.
//
// Parameters:
//
//		factor - multiple to expand a the image vertically, currently only
//				factor of 2 is supported
//
//		pFrameIn  - a frame from QCam
//
//		pFrameOut - you must fill in the following fields:
//						pBuffer		an allocated buffer to hold output image,
//									this must be factor times the original 
//									image size
//						bufferSize	size of the buffer in bytes
//						format		the output format must be the same as the
//									input format, formats allowed are qfmtBayer8
//									and qfmtBayer16
//
// Returns: qerrSuccess on success, error code on failure


QCam_Err QCAMAPI QCam_BayerZoomVert( unsigned char	factor,
									 QCam_Frame*	pFrameIn,
									 QCam_Frame*	pFrameOut);




//===== DATA ==================================================================


#ifdef __cplusplus
} // end extern "C"
#endif

#endif // QCAMIMGFNC_H_INCLUDE

