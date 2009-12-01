//***********************************************************************************************
//
//    Copyright (c) 1999 Axon Instruments.
//    All rights reserved.
//
//***********************************************************************************************
// MODULE:  MCTelegraphs.hpp
// PURPOSE: MultiClamp Commander Telegraph Definitions
// AUTHOR:  Ayman Mobarak, October 1999
//
// MODIFICATIONS:
//          Nick Fitton, March 2001
//             Updated strings for ICLAMP RAW output.
//
//          Nick Fitton, February 2002
//             Updated strings for VCLAMP RAW & SCALED output.
//             Added broadcast message architecture for clients to find all MCC's.
//             Added RAW signal attributes to telegraph struct.
//             Added hardware type identifier to telegraph struct.
//             Bumped version number to 5.
//

#ifndef INC_MCTELEGRAPHS_HPP
#define INC_MCTELEGRAPHS_HPP

////////////////////////////////////////////////
/// MultiClamp Telegraph API Version
////////////////////////////////////////////////
const UINT MCTG_API_VERSION = 5;

////////////////////////////////////////////////
/// Registered Message ID Strings
////////////////////////////////////////////////
static const char* MCTG_OPEN_MESSAGE_STR       = "MultiClampTelegraphOpenMsg";
static const char* MCTG_CLOSE_MESSAGE_STR      = "MultiClampTelegraphCloseMsg";
static const char* MCTG_REQUEST_MESSAGE_STR    = "MultiClampTelegraphRequestMsg";
static const char* MCTG_SCAN_MESSAGE_STR       = "MultiClampTelegraphScanMsg";
static const char* MCTG_RECONNECT_MESSAGE_STR  = "MultiClampTelegraphReconnectMsg";
static const char* MCTG_BROADCAST_MESSAGE_STR  = "MultiClampTelegraphBroadcastMsg";
static const char* MCTG_ID_MESSAGE_STR         = "MultiClampTelegraphIdMsg";

// Notification message for AxMultiClampMsg
#define MC_COMMAND_MESSAGE_STR                   "MultiClampCommandMsg"

////////////////////////////////////////////////
/// Maximum Number of Telegraph Clients per
//  MultiClamp Channel
////////////////////////////////////////////////
const UINT MCTG_MAX_CLIENTS              = 16;

////////////////////////////////////////////////
/// Operating Mode Identifiers
////////////////////////////////////////////////
const UINT MCTG_MODE_VCLAMP              = 0;
const UINT MCTG_MODE_ICLAMP              = 1;
const UINT MCTG_MODE_ICLAMPZERO          = 2;
const UINT MCTG_MODE_NUMCHOICES          = 3;

////////////////////////////////////////////////////
// Operating Mode Names
// Note: The order of these strings must match
//       the operating mode identifiers above.
////////////////////////////////////////////////////
static const char* MCTG_MODE_NAMES[ MCTG_MODE_NUMCHOICES ] =
{
   "V-Clamp",
   "I-Clamp",
   "I = 0"   
};

////////////////////////////////////////////////////
/// Output Signal Mux Identifiers
////////////////////////////////////////////////////
const UINT MCTG_OUT_MUX_COMMAND         = 0;
const UINT MCTG_OUT_MUX_I_MEMBRANE      = 1;
const UINT MCTG_OUT_MUX_V_MEMBRANE      = 2;
const UINT MCTG_OUT_MUX_V_MEMBRANEx100  = 3;
const UINT MCTG_OUT_MUX_I_BATH          = 4;
const UINT MCTG_OUT_MUX_V_BATH          = 5;
const UINT MCTG_OUT_MUX_NUMCHOICES      = 6;

////////////////////////////////////////////////////
// VClamp Signal Names ( long ) for RAW output in VC mode.
// Note: Offset Potential is included in RAW Membrane Potential
//       These strings should _NOT_ be used for SCALED output.
//
// Note: The order of these strings must match
//       the output signal mux identifiers above.
////////////////////////////////////////////////////
static const char* MCTG_OUT_MUX_VC_LONG_NAMES_RAW[ MCTG_OUT_MUX_NUMCHOICES ] =
{
   "Membrane plus Offset Potential",
   "Membrane Current",
   "Pipette Potential",
   "100 x AC Pipette Potential",
   "Bath Current",
   "Bath Potential"
};

////////////////////////////////////////////////////
// VClamp Signal Names ( long )
// Note: The order of these strings must match
//       the output signal mux identifiers above.
////////////////////////////////////////////////////
static const char* MCTG_OUT_MUX_VC_LONG_NAMES[ MCTG_OUT_MUX_NUMCHOICES ] =
{
   "Membrane Potential",
   "Membrane Current",
   "Pipette Potential",
   "100 x AC Pipette Potential",
   "Bath Current",
   "Bath Potential"
};

////////////////////////////////////////////////////
// VClamp Signal Names ( short )
// Note: The order of these strings must match
//       the output signal mux identifiers above.
////////////////////////////////////////////////////
static const char* MCTG_OUT_MUX_VC_SHORT_NAMES[ MCTG_OUT_MUX_NUMCHOICES ] =
{
   "Vm",
   "Im",
   "Vp",
   "100Vp",
   "Ib",
   "Vb"
};

////////////////////////////////////////////////////
// IClamp Signal Names ( long ) for RAW output in IC mode.
// Note: Offset Potential is added to RAW Membrane Potential.
//       These strings should _NOT_ be used for SCALED output.
//
// Note: The order of these strings must match
//       the output signal mux identifiers above.
////////////////////////////////////////////////////
static const char* MCTG_OUT_MUX_IC_LONG_NAMES_RAW[ MCTG_OUT_MUX_NUMCHOICES ] =
{
   "Command Current",
   "Membrane Current",
   "Membrane plus Offset Potential",
   "100 x AC Membrane Potential",
   "Bath Current",
   "Bath Potential"
};

////////////////////////////////////////////////////
// IClamp Signal Names ( long ) for all other output.
// Note: The order of these strings must match
//       the output signal mux identifiers above.
////////////////////////////////////////////////////
static const char* MCTG_OUT_MUX_IC_LONG_NAMES[ MCTG_OUT_MUX_NUMCHOICES ] =
{
   "Command Current",
   "Membrane Current",
   "Membrane Potential",
   "100 x AC Membrane Potential",
   "Bath Current",
   "Bath Potential"
};

////////////////////////////////////////////////////
// IClamp Signal Names ( short )
// Note: The order of these strings must match
//       the output signal mux identifiers above.
////////////////////////////////////////////////////
static const char* MCTG_OUT_MUX_IC_SHORT_NAMES[ MCTG_OUT_MUX_NUMCHOICES ] =
{
   "Ic",
   "Im",
   "Vm",
   "100Vm",
   "Ib",
   "Vb"
};

////////////////////////////////////////////////////
/// Gain Scale Factor Units Identifiers
////////////////////////////////////////////////////
const UINT MCTG_UNITS_VOLTS_PER_VOLT      = 0;
const UINT MCTG_UNITS_VOLTS_PER_MILLIVOLT = 1;
const UINT MCTG_UNITS_VOLTS_PER_MICROVOLT = 2;
const UINT MCTG_UNITS_VOLTS_PER_AMP       = 3;
const UINT MCTG_UNITS_VOLTS_PER_MILLIAMP  = 4;
const UINT MCTG_UNITS_VOLTS_PER_MICROAMP  = 5;
const UINT MCTG_UNITS_VOLTS_PER_NANOAMP   = 6;
const UINT MCTG_UNITS_VOLTS_PER_PICOAMP   = 7;

////////////////////////////////////////////////////
/// Special Telegraph Parameter Value Constants
////////////////////////////////////////////////////
const double MCTG_LPF_BYPASS         = 1.0e+5;
const double MCTG_NOMEMBRANECAP      = 0.0e+0;

////////////////////////////////////////////////////
/// Hardware Type Identifiers
////////////////////////////////////////////////////
const UINT MCTG_HW_TYPE_MC700A      = 0;
const UINT MCTG_HW_TYPE_NUMCHOICES  = 1;

////////////////////////////////////////////////////
/// Hardware Type Names
////////////////////////////////////////////////////
static const char* MCTG_HW_TYPE_NAMES[ MCTG_HW_TYPE_NUMCHOICES ] =
{
   "MultiClamp 700A"
};

////////////////////////////////////////////////////
/// Telegraph Data Structure
////////////////////////////////////////////////////
//
// Note: Explicit alignment directive here.
//       Set struct member alignment to 4 bytes ( i.e. /Zp4 ) in your project.
//
#pragma pack (push,4)
struct MC_TELEGRAPH_DATA
{
   UINT    uVersion;            // must be set to MCTG_API_VERSION

   UINT    uStructSize;         // currently 128 bytes

   UINT    uComPortID;          // ( one-based  counting ) 1 -> 8

   UINT    uAxoBusID;           // ( zero-based counting ) 0 -> 9
                                // A.K.A. "Device Number"

   UINT    uChannelID;          // ( one-based  counting ) 1 -> 2

   UINT    uOperatingMode;      // use constants defined above

   UINT    uScaledOutSignal;    // use constants defined above
                                // for SCALED output signal.

   double  dAlpha;              // scaled output gain (dimensionless)
                                // for SCALED output signal.

   double  dScaleFactor;        // gain scale factor ( for dAlpha == 1 )
                                // for SCALED output signal.

   UINT    uScaleFactorUnits;   // use constants defined above
                                // for SCALED output signal.

   double  dLPFCutoff;          // ( Hz ) , ( MCTG_LPF_BYPASS indicates Bypass )

   double  dMembraneCap;        // ( F  ) 
                                // dMembraneCap will be MCTG_NOMEMBRANECAP
                                // if we are not in V-Clamp mode,
                                // or
                                // if Rf is set to range 2 (5G) or range 3 (50G),
                                // or
                                // if whole cell comp is explicitly disabled.

   double  dExtCmdSens;         // external command sensitivity
                                // ( V/V ) for V-Clamp
                                // ( A/V ) for I-Clamp
                                // 0 (OFF) for I = 0 mode

   UINT    uRawOutSignal;       // use constants defined above
                                // for RAW output signal.

   double  dRawScaleFactor;     // gain scale factor ( for dAlpha == 1 )
                                // for RAW output signal.

   UINT    uRawScaleFactorUnits;// use constants defined above
                                // for RAW output signal.

   UINT    uHardwareType;       // use constants defined above

   char    pcPadding[36];       // room for this structure to grow
};
#pragma pack (pop)


/////////////////////////////////////////////////////////////////////////
//   Format for packed LPARAM of MultiClamp signal identifiers
/////////////////////////////////////////////////////////////////////////
//   ------------------------------------------------------------------   
//   | Byte 3            | Byte 2           | Byte 1    | Byte 0      |
//   ------------------------------------------------------------------
//   | Channel ID (High) | Channel ID (Low) | AxoBus ID | Com Port ID |
//   ------------------------------------------------------------------
/////////////////////////////////////////////////////////////////////////

//--------------------------------------------------------------------
// FUNCTION:   MCTG_PackSignalIDs
// PURPOSE:    Packs MultiClamp signal identifiers into an LPARAM
//             suitable for transmission with a telegraph message.
//
inline LPARAM MCTG_PackSignalIDs( UINT uComPortID,
                                  UINT uAxoBusID,
                                  UINT uChannelID  )
{
   LPARAM lparamSignalIDs = 0;
   lparamSignalIDs |= ( uComPortID       );
   lparamSignalIDs |= ( uAxoBusID  <<  8 );
   lparamSignalIDs |= ( uChannelID << 16 );
   return lparamSignalIDs;
}

//--------------------------------------------------------------------
// FUNCTION:   MCTG_UnpackSignalIDs
// PURPOSE:    Unpacks MultiClamp signal identifiers from an LPARAM
//             used for transmission with a telegraph message.
//
inline BOOL MCTG_UnpackSignalIDs( LPARAM lparamSignalIDs,
                                  UINT *puComPortID,
                                  UINT *puAxoBusID,
                                  UINT *puChannelID       )
{
   if( puComPortID == NULL || puAxoBusID == NULL || puChannelID == NULL )
   {
      return FALSE;
   }

   *puComPortID = ( (UINT) lparamSignalIDs       ) & 0x000000FF;
   *puAxoBusID  = ( (UINT) lparamSignalIDs >>  8 ) & 0x000000FF;
   *puChannelID = ( (UINT) lparamSignalIDs >> 16 ) & 0x0000FFFF;

   return TRUE;
}

//--------------------------------------------------------------------
// FUNCTION:   MCTG_MatchSignalIDs
// PURPOSE:    Determines if the specified MultiClamp signal identifiers
//             match those in the given packed LPARAM
//
inline BOOL   MCTG_MatchSignalIDs( UINT   uComPortID,
                                   UINT   uAxoBusID,
                                   UINT   uChannelID,
                                   LPARAM lparamSignalIDs )
{
   UINT uTelegraphedComPortID = 0;
   UINT uTelegraphedAxoBusID = 0;
   UINT uTelegraphedChannelID = 0;

   if( !MCTG_UnpackSignalIDs( lparamSignalIDs,
                              &uTelegraphedComPortID,
                              &uTelegraphedAxoBusID,
                              &uTelegraphedChannelID ) )
   {
      return FALSE;
   }

   if( ( uComPortID == uTelegraphedComPortID ) &&
       ( uAxoBusID  == uTelegraphedAxoBusID  ) &&
       ( uChannelID == uTelegraphedChannelID )    )
   {
      return TRUE;
   }
   else
   {
      return FALSE;
   }
}


#endif // INC_MCTELEGRAPHS_HPP
