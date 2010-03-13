//***********************************************************************************************
//
//    Copyright (c) 1999-2003 Axon Instruments.
//    All rights reserved.
//
//***********************************************************************************************
// MODULE:  MultiClampBroadcastMsg.hpp
// PURPOSE: MultiClamp Commander Telegraph Definitions and 
//          Notification messages for MultiClamp Commander broadcast messages.
// AUTHOR:  Ayman Mobarak, Oct 1999
//          Guy Burkitt, Dec 2003
//
// MODIFICATIONS:
//          Nick Fitton, Mar 2001
//             Updated strings for ICLAMP RAW output.
//
//          Nick Fitton, Feb 2002
//             Updated strings for VCLAMP RAW & SCALED output.
//             Added broadcast message architecture for clients to find all MCC's.
//             Added RAW signal attributes to telegraph struct.
//             Added hardware type identifier to telegraph struct.
//             Bumped version number to 5.
//
//          Guy Burkitt, Oct 2002
//             Updated and added new signal names to match changes to 700B signals
//             Bumped version number to 6
//
//          Guy Burkitt, Feb 2003
//             Added 700B serial number to telegraph struct
//             Added MCC application, firmware & DSP version strings to telegraph struct
//             Expanded telegraph struct and now must use uStructSize variable to read packet
//             Bumped version number to 7
//
//          Guy Burkitt, Feb 2003
//             Created new lparam packing format for 700B serial number and device channel
//             Added registered message for to scan 700B servers regardless of serial number
//             Added dSecondaryAlpha and dSecondaryLPFCutoff variables to telegraph struct
//             Tagged 700A telegraph struct format as API version = 5
//             Tagged 700B telegraph struct format as most recent API version
//             Added hardware identifier for 700B
//             Bumped version number to 8
//               
//          Guy Burkitt, Mar 2003
//             Changed VC secondary signal name "Membrane + Offset Potential" to "Command Potential". 
//             Bumped version number to 9
//
//          Guy Burkitt, Mar 2003
//             Added SCALED and BNC command telegraph signal identifiers for I and VClamp mode
//             Bumped version number to 10
//
//          Guy Burkitt, Apr 2003
//             Changed all telegraph signal identifiers to have one index per mode per glider.
//             The previous format did not distinguish between a command send to the headstage 
//             or the response measured from the electrode. A command is abbrev. as CMD and
//             a response is abbrev. as MEMB (since it is normally measured at the membrane)
//             These changes allow me to choose any signal order in primary and secondary
//             output gliders. In the previous design the selection had to be the same for 
//             all output gliders. 
//             Update axondev\comp\protocoleditor\SFA_Input_MultiClamp.cpp GRB TODO
//             Bumped version number to 11
//
//          Guy Burkitt, Sep 2003
//             MC_TELEGRAPH_DATA constructor zeros data
//             Added MC_TELEGRAPH_DATA padding up to 256 bytes for future expansion
//             Bumped version number to 12
//
//          Guy Burkitt, Dec 2003
//             This file moved from //depot/toorak/_main/AxonDev/Apps/Multiclamp/Include/MCTelegraphs.hpp
//             to //depot/toorak/_main/AxonDev/Comp/common/MultiClampBroadcastMsg.hpp 
//
//          Guy Burkitt, Nov 2004
//             Added dSeriesResistance to MC_TELEGRAPH_DATA
//             Added Initialize method to MC_TELEGRAPH_DATA (same as old constructor which new one calls)
//             Bumped version number to 13

#ifndef INC_MCBROADCASTMSG_HPP
#define INC_MCBROADCASTMSG_HPP

////////////////////////////////////////////////
/// MultiClamp Telegraph API Version
////////////////////////////////////////////////
const UINT MCTG_API_VERSION      = 13;

const UINT MCTG_API_VERSION_700A = 5;
const UINT MCTG_API_VERSION_700B = MCTG_API_VERSION;

////////////////////////////////////////////////////
/// Hardware Type Identifiers
////////////////////////////////////////////////////
const UINT MCTG_HW_TYPE_MC700A      = 0;
const UINT MCTG_HW_TYPE_MC700B      = 1;
const UINT MCTG_HW_TYPE_NUMCHOICES  = 2;
const UINT MCTG_HW_TYPE_CURRENT     = MCTG_HW_TYPE_MC700B;

////////////////////////////////////////////////////
/// Hardware Type Names
////////////////////////////////////////////////////
static const char* MCTG_HW_TYPE_NAMES[ MCTG_HW_TYPE_NUMCHOICES ] =
{
   "MultiClamp 700A",
   "MultiClamp 700B"
};

////////////////////////////////////////////////
/// Registered Message ID Strings
////////////////////////////////////////////////

// Notification messages for telegraphs
static const char* MCTG_OPEN_MESSAGE_STR       = "MultiClampTelegraphOpenMsg";
static const char* MCTG_CLOSE_MESSAGE_STR      = "MultiClampTelegraphCloseMsg";
static const char* MCTG_REQUEST_MESSAGE_STR    = "MultiClampTelegraphRequestMsg";
static const char* MCTG_SCAN_MESSAGE_STR       = "MultiClampTelegraphScanMsg";
static const char* MCTG_RECONNECT_MESSAGE_STR  = "MultiClampTelegraphReconnectMsg";
static const char* MCTG_BROADCAST_MESSAGE_STR  = "MultiClampTelegraphBroadcastMsg";
static const char* MCTG_ID_MESSAGE_STR         = "MultiClampTelegraphIdMsg";

// Notification messages for CFR part 11 compliance
#define MC_CONFIGREQUEST_MESSAGE_STR  "MultiClampConfigRequestMsg"
#define MC_CONFIGSENT_MESSAGE_STR     "MultiClampConfigSentMsg"
#define MC_COMMANDERLOCK_MESSAGE_STR  "MultiClampCommanderLock"

// Notification message for AxMultiClampMsg
#define MC_COMMAND_MESSAGE_STR        "MultiClampCommandMsg"

// Defines for lParam in MC_COMMANDERLOCK_MESSAGE_STR message
#define MC_COMMANDER_LOCK             1
#define MC_COMMANDER_UNLOCK           2

// Clipboard size in bytes for multiclamp configuration data
#define MC_CFG_SIZE                   20000

////////////////////////////////////////////////
/// Maximum Number of Telegraph Clients/Servers
//  per MultiClamp Channel
////////////////////////////////////////////////
const UINT MCTG_MAX_CLIENTS              = 16;
const UINT MCTG_MAX_SERVERS              = 256;

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
/// 700A Telegraph Output Signal Mux Identifiers
////////////////////////////////////////////////////
const UINT MCTG_OUT_MUX_I_CMD_SUMMED    = 0;
const UINT MCTG_OUT_MUX_V_CMD_SUMMED    = 1;
const UINT MCTG_OUT_MUX_I_CMD_EXT       = 2;
const UINT MCTG_OUT_MUX_V_CMD_EXT       = 3;
const UINT MCTG_OUT_MUX_I_MEMBRANE      = 4;
const UINT MCTG_OUT_MUX_V_MEMBRANE      = 5;
const UINT MCTG_OUT_MUX_V_MEMBRANEx100  = 6;
const UINT MCTG_OUT_MUX_I_AUX1          = 7;
const UINT MCTG_OUT_MUX_V_AUX1          = 8;
const UINT MCTG_OUT_MUX_I_AUX2          = 9;
const UINT MCTG_OUT_MUX_V_AUX2          = 10;
const UINT MCTG_OUT_MUX_NUMCHOICES      = 11;

///////////////////////////////////////////////////////////////
/// 700B Primary and Secondary Output Signal Constants
///////////////////////////////////////////////////////////////

// These indices represent a unique index to distingish properties
// of the signal such as primary and secondary output, voltage or 
// current clamp, membrane signal, external command, summed internal
// command or headstage command

// VC Primary
const long   AXMCD_OUT_PRI_VC_GLDR_MIN            = 0;
const long   AXMCD_OUT_PRI_VC_GLDR_MAX            = 6;

const long   AXMCD_OUT_PRI_VC_GLDR_I_MEMB         = 0;
const long   AXMCD_OUT_PRI_VC_GLDR_V_CMD_SUMMED   = 1;
const long   AXMCD_OUT_PRI_VC_GLDR_V_CMD_MEMB     = 2;
const long   AXMCD_OUT_PRI_VC_GLDR_V_CMD_MEMBx100 = 3;
const long   AXMCD_OUT_PRI_VC_GLDR_V_CMD_EXT      = 4;
const long   AXMCD_OUT_PRI_VC_GLDR_AUX1           = 5;
const long   AXMCD_OUT_PRI_VC_GLDR_AUX2           = 6;

// VC Secondary
const long   AXMCD_OUT_SEC_VC_GLDR_MIN            = 10;
const long   AXMCD_OUT_SEC_VC_GLDR_MAX            = 16;

const long   AXMCD_OUT_SEC_VC_GLDR_I_MEMB         = 10;
const long   AXMCD_OUT_SEC_VC_GLDR_V_CMD_MEMBx10  = 11;
const long   AXMCD_OUT_SEC_VC_GLDR_V_CMD_SUMMED   = 12;
const long   AXMCD_OUT_SEC_VC_GLDR_V_CMD_MEMBx100 = 13;
const long   AXMCD_OUT_SEC_VC_GLDR_V_CMD_EXT      = 14;
const long   AXMCD_OUT_SEC_VC_GLDR_AUX1           = 15;
const long   AXMCD_OUT_SEC_VC_GLDR_AUX2           = 16;

// IC Primary
const long   AXMCD_OUT_PRI_IC_GLDR_MIN            = 20;
const long   AXMCD_OUT_PRI_IC_GLDR_MAX            = 26;

const long   AXMCD_OUT_PRI_IC_GLDR_V_MEMBx10      = 20;
const long   AXMCD_OUT_PRI_IC_GLDR_I_CMD_MEMB     = 21;
const long   AXMCD_OUT_PRI_IC_GLDR_I_CMD_SUMMED   = 22;
const long   AXMCD_OUT_PRI_IC_GLDR_V_MEMBx100     = 23;
const long   AXMCD_OUT_PRI_IC_GLDR_I_CMD_EXT      = 24;
const long   AXMCD_OUT_PRI_IC_GLDR_AUX1           = 25;
const long   AXMCD_OUT_PRI_IC_GLDR_AUX2           = 26;

// IC Secondary
const long   AXMCD_OUT_SEC_IC_GLDR_MIN            = 30;
const long   AXMCD_OUT_SEC_IC_GLDR_MAX            = 36;

const long   AXMCD_OUT_SEC_IC_GLDR_V_MEMBx10      = 30;
const long   AXMCD_OUT_SEC_IC_GLDR_I_CMD_MEMB     = 31;
const long   AXMCD_OUT_SEC_IC_GLDR_V_MEMB         = 32;
const long   AXMCD_OUT_SEC_IC_GLDR_V_MEMBx100     = 33;
const long   AXMCD_OUT_SEC_IC_GLDR_I_CMD_EXT      = 34;
const long   AXMCD_OUT_SEC_IC_GLDR_AUX1           = 35;
const long   AXMCD_OUT_SEC_IC_GLDR_AUX2           = 36;

// Auxiliary signals (each auxiliary glider index maps to one of these)
const long   AXMCD_OUT_V_AUX1                     = 40;
const long   AXMCD_OUT_I_AUX1                     = 41;
const long   AXMCD_OUT_V_AUX2                     = 42;
const long   AXMCD_OUT_I_AUX2                     = 43;
const long   AXMCD_OUT_NOTCONNECTED_AUX           = 44;
const long   AXMCD_OUT_RESERVED_AUX               = 45;
const long   AXMCD_OUT_NOT_AUX                    = 46;

// Number of signal choices available
const long   AXMCD_OUT_NAMES_NUMCHOICES           = 40;
const long   AXMCD_OUT_CACHE_NUMCHOICES           = 7;

////////////////////////////////////////////////////
// Signal Names ( long )
////////////////////////////////////////////////////
static const char* MCTG_OUT_GLDR_LONG_NAMES[ AXMCD_OUT_NAMES_NUMCHOICES ] =
{
   "Membrane Current",              // VC primary output signal glider names
   "Membrane Potential",
   "Pipette Potential",
   "100x AC Membrane Potential",
   "External Command Potential",
   "Auxiliary 1",
   "Auxiliary 2",
   "Not Used",
   "Not Used",
   "Not Used",
   "Membrane Current",              // VC secondary output signal glider names
   "Membrane Potential",
   "Pipette Potential",
   "100x AC Membrane Potential",
   "External Command Potential",
   "Auxiliary 1",
   "Auxiliary 2",
   "Not Used",
   "Not Used",
   "Not Used",
   "Membrane Potential",            // IC primary output signal glider names
   "Membrane Current",
   "Command Current",
   "100x AC Membrane Potential",
   "External Command Current",
   "Auxiliary 1",
   "Auxiliary 2",
   "Not Used",
   "Not Used",
   "Not Used",
   "Membrane Potential",             // IC secondary output signal glider names
   "Membrane Current",
   "Pipette Potential",
   "100x AC Membrane Potential",
   "External Command Current",
   "Auxiliary 1",
   "Auxiliary 2",
   "Not Used",
   "Not Used",
   "Not Used"
};

////////////////////////////////////////////////////
// Signal Names ( short )
////////////////////////////////////////////////////
static const char* MCTG_OUT_GLDR_SHORT_NAMES[] =
{
   "Im",     // VC primary output signal glider names
   "Vm",
   "Vp",
   "100Vp",
   "Vext",
   "Aux1",
   "Aux2",
   "Not Used",
   "Not Used",
   "Not Used",
   "Im",     // VC secondary output signal glider names
   "Vm",
   "Vm",
   "100Vp",
   "Vext",
   "Aux1",
   "Aux2",
   "Not Used",
   "Not Used",
   "Not Used",
   "Vm",     // IC primary output signal glider names
   "Im",
   "Ic",
   "100Vp",
   "Vext",
   "Aux1",
   "Aux2",
   "Not Used",
   "Not Used",
   "Not Used",
   "Vm",     // IC secondary output signal glider names
   "Im",
   "Vp",
   "100Vp",
   "Vext",
   "Aux1",
   "Aux2",
   "Not Used",
   "Not Used",
   "Not Used"
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
const UINT MCTG_UNITS_NONE                = 8;

////////////////////////////////////////////////////
/// Special Telegraph Parameter Value Constants
////////////////////////////////////////////////////
const double MCTG_LPF_BYPASS         = 1.0e+5;
const double MCTG_NOMEMBRANECAP      = 0.0e+0;
const double MCTG_NOSERIESRESIST     = 0.0e+0;

////////////////////////////////////////////////////
/// Telegraph Data Structure
////////////////////////////////////////////////////
//
// Note: Explicit alignment directive here.
//       Set struct member alignment to 4 bytes ( i.e. /Zp4 ) in your project.
//       It you extend this structure be sure to bump the API version
//
#pragma pack (push,4)
struct MC_TELEGRAPH_DATA
{
   UINT    uVersion;              // must be set to MCTG_API_VERSION

   UINT    uStructSize;           // must be set to sizeof( MC_TELEGRAPH_DATA )
                                  // uVersion <= 6 was 128 bytes, expanded size for uVersion > 6 

   UINT    uComPortID;            // ( one-based  counting ) 1 -> 8

   UINT    uAxoBusID;             // ( zero-based counting ) 0 -> 9
                                  // A.K.A. "Device Number"

   UINT    uChannelID;            // ( one-based  counting ) 1 -> 2

   UINT    uOperatingMode;        // use constants defined above

   UINT    uScaledOutSignal;      // use constants defined above
                                  // for PRIMARY output signal.

   double  dAlpha;                // output gain (dimensionless)
                                  // for PRIMARY output signal.

   double  dScaleFactor;          // gain scale factor ( for dAlpha == 1 )
                                  // for PRIMARY output signal.

   UINT    uScaleFactorUnits;     // use constants defined above
                                  // for PRIMARY output signal.

   double  dLPFCutoff;            // ( Hz ) , ( MCTG_LPF_BYPASS indicates Bypass )

   double  dMembraneCap;          // ( F  ) 
                                  // dMembraneCap will be MCTG_NOMEMBRANECAP
                                  // if we are not in V-Clamp mode,
                                  // or
                                  // if Rf is set to range 2 (5G) or range 3 (50G),
                                  // or
                                  // if whole cell comp is explicitly disabled.

   double  dExtCmdSens;           // external command sensitivity
                                  // ( V/V ) for V-Clamp
                                  // ( A/V ) for I-Clamp
                                  // 0 (OFF) for I = 0 mode

   UINT    uRawOutSignal;         // use constants defined above
                                  // for SECONDARY output signal.

   double  dRawScaleFactor;       // gain scale factor ( for Alpha == 1 )
                                  // for SECONDARY output signal.

   UINT    uRawScaleFactorUnits;  // use constants defined above
                                  // for SECONDARY output signal.

   UINT    uHardwareType;         // use constants defined above

   double  dSecondaryAlpha;       // output gain (dimensionless)
                                  // for SECONDARY output signal.

   double  dSecondaryLPFCutoff;   // ( Hz ) , ( MCTG_LPF_BYPASS indicates Bypass )
                                  // for SECONDARY output signal.

   char    szAppVersion[16];      // application version number

   char    szFirmwareVersion[16]; // firmware version number

   char    szDSPVersion[16];      // DSP version number

   char    szSerialNumber[16];    // serial number of device

   double  dSeriesResistance;     // ( Rs ) 
                                  // dSeriesResistance will be MCTG_NOSERIESRESIST
                                  // if we are not in V-Clamp mode,
                                  // or
                                  // if Rf is set to range 2 (5G) or range 3 (50G),
                                  // or
                                  // if whole cell comp is explicitly disabled.

   char    pcPadding[76];         // room for this structure to grow

   void Initialize()   { memset(this, 0, sizeof(*this)); }
   MC_TELEGRAPH_DATA() { Initialize(); }
}; // sizeof(MC_TELEGRAPH_DATA) = 256

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
// FUNCTION:   MCTG_Pack700ASignalIDs
// PURPOSE:    Packs MultiClamp signal identifiers into an LPARAM
//             suitable for transmission with a telegraph message.
//
inline LPARAM MCTG_Pack700ASignalIDs( UINT uComPortID,
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
// FUNCTION:   MCTG_Unpack700ASignalIDs
// PURPOSE:    Unpacks MultiClamp signal identifiers from an LPARAM
//             used for transmission with a telegraph message.
//
inline BOOL MCTG_Unpack700ASignalIDs( LPARAM lparamSignalIDs,
                                      UINT   *puComPortID,
                                      UINT   *puAxoBusID,
                                      UINT   *puChannelID       )
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
// FUNCTION:   MCTG_Match700ASignalIDs
// PURPOSE:    Determines if the specified MultiClamp signal identifiers
//             match those in the given packed LPARAM
//
inline BOOL   MCTG_Match700ASignalIDs( UINT   uComPortID,
                                       UINT   uAxoBusID,
                                       UINT   uChannelID,
                                       LPARAM lparamSignalIDs )
{
   UINT uTelegraphedComPortID = 0;
   UINT uTelegraphedAxoBusID = 0;
   UINT uTelegraphedChannelID = 0;

   if( !MCTG_Unpack700ASignalIDs( lparamSignalIDs,
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


//////////////////////////////////////////////////////////////////////////////
//   Format for packed LPARAM of MultiClamp 700B signal identifiers
//////////////////////////////////////////////////////////////////////////////
//   -------------------------------------------------------------------------   
//   | Byte 3 (high nibble) | Byte 3 (low nibble) | Byte 2 | Byte 1 | Byte 0 |
//   -------------------------------------------------------------------------
//   | Channel ID (4bits)   | Serial Number (28 bits)                        |
//   -------------------------------------------------------------------------
//////////////////////////////////////////////////////////////////////////////

//--------------------------------------------------------------------
// FUNCTION:   MCTG_Pack700BSignalIDs
// PURPOSE:    Packs MultiClamp signal identifiers into an LPARAM
//             suitable for transmission with a telegraph message.
//
inline LPARAM MCTG_Pack700BSignalIDs( UINT uSerialNum,
                                      UINT uChannelID  )
{
   LPARAM lparamSignalIDs = 0;
   lparamSignalIDs |= ( uSerialNum & 0x0FFFFFFF );
   lparamSignalIDs |= ( uChannelID << 28 );
   return lparamSignalIDs;
}

//--------------------------------------------------------------------
// FUNCTION:   MCTG_Unpack700BSignalIDs
// PURPOSE:    Unpacks MultiClamp signal identifiers from an LPARAM
//             used for transmission with a telegraph message.
//
inline BOOL MCTG_Unpack700BSignalIDs( LPARAM lparamSignalIDs,
                                      UINT   *puSerialNum,
                                      UINT   *puChannelID       )
{
   if( puSerialNum == NULL || puChannelID == NULL )
      return FALSE;

   *puSerialNum = ( (UINT) lparamSignalIDs       ) & 0x0FFFFFFF;
   *puChannelID = ( (UINT) lparamSignalIDs >> 28 ) & 0x0000000F;

   return TRUE;
}

//--------------------------------------------------------------------
// FUNCTION:   MCTG_Match700BSignalIDs
// PURPOSE:    Determines if the specified MultiClamp signal identifiers
//             match those in the given packed LPARAM
//
inline BOOL   MCTG_Match700BSignalIDs( UINT   uSerialNum,
                                       UINT   uChannelID,
                                       LPARAM lparamSignalIDs )
{
   UINT uTelegraphedSerialNum = 0;
   UINT uTelegraphedChannelID = 0;

   if( !MCTG_Unpack700BSignalIDs( lparamSignalIDs,
                                  &uTelegraphedSerialNum,
                                  &uTelegraphedChannelID ) )
   {  
      return FALSE;
   }

   if( ( uSerialNum == uTelegraphedSerialNum ) &&
       ( uChannelID == uTelegraphedChannelID )    )
   {
      return TRUE;
   }
   else
   {
      return FALSE;
   }
}

#endif // INC_MCBROADCASTMSG_HPP
