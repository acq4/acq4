/*
|==============================================================================
| Copyright (C) 2000 Quantitative Imaging Corporation.  All Rights Reserved.
| Reproduction or disclosure of this file or its contents without the prior
| written consent of Quantitative Imaging Corporation is prohibited.
|==============================================================================
|
| File:			QImgTypes.h
|
| Project/lib:	
|
| Target:		All
|
| Description:	Basic types for internal use.
|
| Notes:		
|
|==============================================================================
| dd/mon/yy  Author		Notes
|------------------------------------------------------------------------------
| 30/Aug/00  DavidL		Original.
|==============================================================================
*/

#ifndef QIMGTYPES_H_INCLUDE
#define QIMGTYPES_H_INCLUDE

//===== INCLUDE FILES =========================================================

#ifdef _DEBUG
#include <assert.h>
#endif

//===== #DEFINES ==============================================================

#define EXPORT
#define IMPORT			extern
#define PRIVATE			static

#ifndef ASSERT
#ifdef _DEBUG
#define ASSERT( e )		assert( e )
#else
#define ASSERT( e )
#endif
#endif // ASSERT defined

//===== TYPE DEFINITIONS ======================================================

#ifndef INTEGRAL_TYPES
#define INTEGRAL_TYPES

	#if defined (_MSC_VER)
		typedef unsigned __int64	uint64;
		typedef __int64				int64;
	#else
		typedef unsigned long long	uint64;
		typedef long long			int64;
	#endif // defined (_MSC_VER)

	typedef unsigned long	uint32;
	typedef signed long		int32;
	typedef unsigned short	uint16;
	typedef signed short	int16;
	typedef unsigned char	uint8;
	typedef signed char		int8;
	typedef unsigned char	byte;

	#ifndef __cplusplus
		typedef enum { false=0, true=1, _bool_force32=0xFFFFFFFF } bool;
	#endif // __cplusplus

	typedef	float			float32;			// IEEE 32 bit

	#if defined (__MWERKS__) || defined (THINK_C)
		typedef	short double	float64;
	#else
		typedef double			float64;		// IEEE 64 bit
	#endif // defined (__MWERKS__) || defined (THINK_C)

#endif // INTEGRAL_TYPES

//===== FUNCTION PROTOTYPES ===================================================

//===== DATA ==================================================================


#endif // QIMGTYPES_H_INCLUDE

