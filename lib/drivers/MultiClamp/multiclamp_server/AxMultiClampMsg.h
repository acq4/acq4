//***********************************************************************************************
//
//    Copyright (c) 2004 Axon Instruments.
//    All rights reserved.
//
//***********************************************************************************************
// MODULE:  AXMULTICLAMPMSG.HPP
// PURPOSE: Interface definition for AxMultiClampMsg.DLL
// AUTHOR:  GRB  Mar 2004
//

#ifndef INC_AXMULTICLAMPMSG_HPP
#define INC_AXMULTICLAMPMSG_HPP

#if _MSC_VER >= 1000
#pragma once
#endif // _MSC_VER >= 1000

// define the macro for exporting/importing the API entry points.
// N.B. the symbol below should only be defined when building this DLL.
#ifdef MAK_AXMCCMSG_DLL
   #define AXMCCMSG   __declspec(dllexport)
#else
   #define AXMCCMSG   __declspec(dllimport)
#endif

extern "C" {

// The handle type declaration.
DECLARE_HANDLE(HMCCMSG);

// API version number.
#define MCCMSG_APIVERSION       1,0,0,7
#define MCCMSG_APIVERSION_STR  "1.0.0.7"

// Windows Class name for the MultiClamp Commander msg handler hidden window.
#define MCCMSG_CLASSNAME "MultiClampMessageHandlerClass"

//==============================================================================================
// DLL creation/destruction functions
//==============================================================================================

// Check on the version number of the API interface.
AXMCCMSG BOOL WINAPI MCCMSG_CheckAPIVersion(LPCSTR pszQueryVersion);

// Create the MultiClamp Commander message handler object.
AXMCCMSG HMCCMSG WINAPI MCCMSG_CreateObject(int *pnError);

// Destroy the MultiClamp Commander message handler object.
AXMCCMSG void  WINAPI MCCMSG_DestroyObject(HMCCMSG hMCCmsg);

//==============================================================================================
// General functions
//==============================================================================================

// Set timeout in milliseconds for messages to MultiClamp Commander.
AXMCCMSG BOOL WINAPI MCCMSG_SetTimeOut(HMCCMSG hMCCmsg, UINT uTimeOutMS, int *pnError);

//==============================================================================================
// MultiClamp 700x Commander selection functions
//==============================================================================================

// Find the first MultiClamp Commander and return device info
AXMCCMSG BOOL WINAPI MCCMSG_FindFirstMultiClamp(HMCCMSG hMCCmsg, UINT *puModel, char *pszSerialNum, UINT uBufSize, UINT *puCOMPortID, UINT *puDeviceID, UINT *puChannelID, int *pnError);

// Find next MultiClamp Commander and return device info, returns FALSE when all MultiClamp Commanders have been found
AXMCCMSG BOOL WINAPI MCCMSG_FindNextMultiClamp(HMCCMSG hMCCmsg, UINT *puModel, char *pszSerialNum, UINT uBufSize, UINT *puCOMPortID, UINT *puDeviceID, UINT *puChannelID, int *pnError);

// Select MultiClamp Commander for communication, returns TRUE if communication established
AXMCCMSG BOOL WINAPI MCCMSG_SelectMultiClamp(HMCCMSG hMCCmsg, UINT uModel, char *pszSerialNum, UINT uCOMPortID, UINT uDeviceID, UINT uChannelID, int *pnError);

//==============================================================================================
// MCC Mode functions
//==============================================================================================

// Set the amplifier mode i.e voltage clamp, current clamp, or current = 0
AXMCCMSG BOOL WINAPI MCCMSG_SetMode(HMCCMSG hMCCmsg, UINT uModeID, int *pnError);

// Get the amplifier mode i.e voltage clamp, current clamp, or current = 0
AXMCCMSG BOOL WINAPI MCCMSG_GetMode(HMCCMSG hMCCmsg, UINT *puModeID, int *pnError);

// Set auto or external mode switching enable
AXMCCMSG BOOL WINAPI MCCMSG_SetModeSwitchEnable(HMCCMSG hMCCmsg, BOOL bEnable, int *pnError);

// Get auto or external mode switching enable
AXMCCMSG BOOL WINAPI MCCMSG_GetModeSwitchEnable(HMCCMSG hMCCmsg, BOOL *pbEnable, int *pnError);


//==============================================================================================
// MCC Holding functions
//==============================================================================================

// Set holding enable (voltage clamp or current clamp)
AXMCCMSG BOOL WINAPI MCCMSG_SetHoldingEnable(HMCCMSG hMCCmsg, BOOL bEnable, int *pnError);

// Get holding enable (voltage clamp or current clamp)
AXMCCMSG BOOL WINAPI MCCMSG_GetHoldingEnable(HMCCMSG hMCCmsg, BOOL *pbEnable, int *pnError);

// Set holding level (voltage clamp or current clamp)
AXMCCMSG BOOL WINAPI MCCMSG_SetHolding(HMCCMSG hMCCmsg, double dHolding, int *pnError);

// Get holding level (voltage clamp or current clamp)
AXMCCMSG BOOL WINAPI MCCMSG_GetHolding(HMCCMSG hMCCmsg, double *pdHolding, int *pnError);

//==============================================================================================
// MCC Seal Test and Tuning functions
//==============================================================================================

// Set test signal enable
AXMCCMSG BOOL WINAPI MCCMSG_SetTestSignalEnable(HMCCMSG hMCCmsg, BOOL bEnable, int *pnError);

// Set test signal enable
AXMCCMSG BOOL WINAPI MCCMSG_GetTestSignalEnable(HMCCMSG hMCCmsg, BOOL *pbEnable, int *pnError);

// Set test signal amplitude (VC = Seal Test amplitude, IC = Tuning amplitude)
AXMCCMSG BOOL WINAPI MCCMSG_SetTestSignalAmplitude(HMCCMSG hMCCmsg, double dAmplitude, int *pnError);

// Get test signal amplitude (VC = Seal Test amplitude, IC = Tuning amplitude)
AXMCCMSG BOOL WINAPI MCCMSG_GetTestSignalAmplitude(HMCCMSG hMCCmsg, double *pdAmplitude, int *pnError);

// Set test signal frequency (VC = Seal Test frequency, IC = Tuning frequency)
AXMCCMSG BOOL WINAPI MCCMSG_SetTestSignalFrequency(HMCCMSG hMCCmsg, double dFrequency, int *pnError);

// Get test signal frequency (VC = Seal Test frequency, IC = Tuning frequency)
AXMCCMSG BOOL WINAPI MCCMSG_GetTestSignalFrequency(HMCCMSG hMCCmsg, double *pdFrequency, int *pnError);

//==============================================================================================
// MCC Pipette Offset functions
//==============================================================================================

// Execute auto pipette offset
AXMCCMSG BOOL WINAPI MCCMSG_AutoPipetteOffset(HMCCMSG hMCCmsg, int *pnError);

// Set pipette offset
AXMCCMSG BOOL WINAPI MCCMSG_SetPipetteOffset(HMCCMSG hMCCmsg, double dPipetteOffset, int *pnError);

// Get pipette offset
AXMCCMSG BOOL WINAPI MCCMSG_GetPipetteOffset(HMCCMSG hMCCmsg, double *pdPipetteOffset, int *pnError);

//==============================================================================================
// MCC Inject Slow Current functions (IC only)
//==============================================================================================

// Set slow current injection enable
AXMCCMSG BOOL WINAPI MCCMSG_SetSlowCurrentInjEnable(HMCCMSG hMCCmsg, BOOL bEnable, int *pnError);

// Set slow current injection enable
AXMCCMSG BOOL WINAPI MCCMSG_GetSlowCurrentInjEnable(HMCCMSG hMCCmsg, BOOL *pbEnable, int *pnError);

// Set slow current injection level (volts)
AXMCCMSG BOOL WINAPI MCCMSG_SetSlowCurrentInjLevel(HMCCMSG hMCCmsg, double dLevel, int *pnError);

// Get slow current injection level(volts)
AXMCCMSG BOOL WINAPI MCCMSG_GetSlowCurrentInjLevel(HMCCMSG hMCCmsg, double *pdLevel, int *pnError);

// Set slow current injection settling time to 99% of final value (seconds) 
AXMCCMSG BOOL WINAPI MCCMSG_SetSlowCurrentInjSettlingTime(HMCCMSG hMCCmsg, double dSettlingTime, int *pnError);

// Get slow current injection settling time to 99% of final value (seconds) 
AXMCCMSG BOOL WINAPI MCCMSG_GetSlowCurrentInjSettlingTime(HMCCMSG hMCCmsg, double *pdSettlingTime, int *pnError);

//==============================================================================================
// MCC Compensation functions (VC only)
//==============================================================================================

// Set the fast compensation capacitance
AXMCCMSG BOOL WINAPI MCCMSG_SetFastCompCap(HMCCMSG hMCCmsg, double dFastCompCap, int *pnError);

// Get the fast compensation capacitance
AXMCCMSG BOOL WINAPI MCCMSG_GetFastCompCap(HMCCMSG hMCCmsg, double *pdFastCompCap, int *pnError);

// Set the slow compensation capacitance
AXMCCMSG BOOL WINAPI MCCMSG_SetSlowCompCap(HMCCMSG hMCCmsg, double dSlowCompCap, int *pnError);

// Get the slow compensation capacitance
AXMCCMSG BOOL WINAPI MCCMSG_GetSlowCompCap(HMCCMSG hMCCmsg, double *pdSlowCompCap, int *pnError);

// Set the fast compensation time constant
AXMCCMSG BOOL WINAPI MCCMSG_SetFastCompTau(HMCCMSG hMCCmsg, double dFastCompTau, int *pnError);

// Get the fast compensation time constant
AXMCCMSG BOOL WINAPI MCCMSG_GetFastCompTau(HMCCMSG hMCCmsg, double *pdFastCompTau, int *pnError);

// Set the slow compensation time constant
AXMCCMSG BOOL WINAPI MCCMSG_SetSlowCompTau(HMCCMSG hMCCmsg, double dSlowCompTau, int *pnError);

// Get the slow compensation time constant
AXMCCMSG BOOL WINAPI MCCMSG_GetSlowCompTau(HMCCMSG hMCCmsg, double *pdSlowCompTau, int *pnError);

// Set x20 slow compensation time constant enable
AXMCCMSG BOOL WINAPI MCCMSG_SetSlowCompTauX20Enable(HMCCMSG hMCCmsg, BOOL bEnable, int *pnError);

// Get x20 slow compensation time constant enable
AXMCCMSG BOOL WINAPI MCCMSG_GetSlowCompTauX20Enable(HMCCMSG hMCCmsg, BOOL *pbEnable, int *pnError);

// Execute auto fast compensation
AXMCCMSG BOOL WINAPI MCCMSG_AutoFastComp(HMCCMSG hMCCmsg, int *pnError);

// Execute auto slow compensation
AXMCCMSG BOOL WINAPI MCCMSG_AutoSlowComp(HMCCMSG hMCCmsg, int *pnError);

//==============================================================================================
// MCC Pipette Capacitance Neutralization functions (IC only)
//==============================================================================================

// Set Pipette Capacitance Neutralization enable
AXMCCMSG BOOL WINAPI MCCMSG_SetNeutralizationEnable(HMCCMSG hMCCmsg, BOOL bEnable, int *pnError);

// Get Pipette Capacitance Neutralization enable
AXMCCMSG BOOL WINAPI MCCMSG_GetNeutralizationEnable(HMCCMSG hMCCmsg, BOOL *pbEnable, int *pnError);

// Set Pipette Capacitance Neutralization capacitance
AXMCCMSG BOOL WINAPI MCCMSG_SetNeutralizationCap(HMCCMSG hMCCmsg, double dCap, int *pnError);

// Get Pipette Capacitance Neutralization capacitance
AXMCCMSG BOOL WINAPI MCCMSG_GetNeutralizationCap(HMCCMSG hMCCmsg, double *pdCap, int *pnError);

//==============================================================================================
// MCC Whole Cell functions (VC only)
//==============================================================================================

// Set whole cell compensation enable
AXMCCMSG BOOL WINAPI MCCMSG_SetWholeCellCompEnable(HMCCMSG hMCCmsg, BOOL bEnable, int *pnError);

// Get whole cell compensation enable
AXMCCMSG BOOL WINAPI MCCMSG_GetWholeCellCompEnable(HMCCMSG hMCCmsg, BOOL *pbEnable, int *pnError);

// Set whole cell compensation capacitance
AXMCCMSG BOOL WINAPI MCCMSG_SetWholeCellCompCap(HMCCMSG hMCCmsg, double dCap, int *pnError);

// Get whole cell compensation capacitance
AXMCCMSG BOOL WINAPI MCCMSG_GetWholeCellCompCap(HMCCMSG hMCCmsg, double *pdCap, int *pnError);

// Set whole cell compensation resistance
AXMCCMSG BOOL WINAPI MCCMSG_SetWholeCellCompResist(HMCCMSG hMCCmsg, double dResist, int *pnError);

// Get whole cell compensation resistance
AXMCCMSG BOOL WINAPI MCCMSG_GetWholeCellCompResist(HMCCMSG hMCCmsg, double *pdResist, int *pnError);

// Execute auto whole cell compensation
AXMCCMSG BOOL WINAPI MCCMSG_AutoWholeCellComp(HMCCMSG hMCCmsg, int *pnError);

//==============================================================================================
// MCC Rs Compensation functions (VC only)
//==============================================================================================

// Set Rs compensation enable
AXMCCMSG BOOL WINAPI MCCMSG_SetRsCompEnable(HMCCMSG hMCCmsg, BOOL bEnable, int *pnError);

// Get Rs compensation enable
AXMCCMSG BOOL WINAPI MCCMSG_GetRsCompEnable(HMCCMSG hMCCmsg, BOOL *pbEnable, int *pnError);

// Set Rs compensation bandwidth
AXMCCMSG BOOL WINAPI MCCMSG_SetRsCompBandwidth(HMCCMSG hMCCmsg, double dBandwidth, int *pnError);

// Get Rs compensation bandwidth
AXMCCMSG BOOL WINAPI MCCMSG_GetRsCompBandwidth(HMCCMSG hMCCmsg, double *pdBandwidth, int *pnError);

// Set Rs compensation correction
AXMCCMSG BOOL WINAPI MCCMSG_SetRsCompCorrection(HMCCMSG hMCCmsg, double dCorrection, int *pnError);

// Get Rs compensation correction
AXMCCMSG BOOL WINAPI MCCMSG_GetRsCompCorrection(HMCCMSG hMCCmsg, double *pdCorrection, int *pnError);

// Set Rs compensation prediction
AXMCCMSG BOOL WINAPI MCCMSG_SetRsCompPrediction(HMCCMSG hMCCmsg, double dPrediction, int *pnError);

// Get Rs compensation prediction
AXMCCMSG BOOL WINAPI MCCMSG_GetRsCompPrediction(HMCCMSG hMCCmsg, double *pdPrediction, int *pnError);

//==============================================================================================
// MCC Oscillation Killer functions
//==============================================================================================

// Set oscillation killer enable 
AXMCCMSG BOOL WINAPI MCCMSG_SetOscKillerEnable(HMCCMSG hMCCmsg, BOOL bEnable, int *pnError);

// Get oscillation killer enable (VC = Rs Comp, IC = Pip Cap Neut)
AXMCCMSG BOOL WINAPI MCCMSG_GetOscKillerEnable(HMCCMSG hMCCmsg, BOOL *pbEnable, int *pnError);

//==============================================================================================
// MCC Primary (or Scaled) Signal functions
//==============================================================================================

// Set primary signal
AXMCCMSG BOOL WINAPI MCCMSG_SetPrimarySignal(HMCCMSG hMCCmsg, UINT uSignalID, int *pnError);

// Get primary signal
AXMCCMSG BOOL WINAPI MCCMSG_GetPrimarySignal(HMCCMSG hMCCmsg, UINT *puSignalID, int *pnError);

// Set primary signal gain
AXMCCMSG BOOL WINAPI MCCMSG_SetPrimarySignalGain(HMCCMSG hMCCmsg, double dGain, int *pnError);

// Get primary signal gain
AXMCCMSG BOOL WINAPI MCCMSG_GetPrimarySignalGain(HMCCMSG hMCCmsg, double *pdGain, int *pnError);

// Set primary signal lowpass filter cut-off frequency (Bessel or Butterworth)
AXMCCMSG BOOL WINAPI MCCMSG_SetPrimarySignalLPF(HMCCMSG hMCCmsg, double dLPF, int *pnError);

// Get primary signal lowpass filter cut-off frequency (Bessel or Butterworth)
AXMCCMSG BOOL WINAPI MCCMSG_GetPrimarySignalLPF(HMCCMSG hMCCmsg, double *pdLPF, int *pnError);

// Set primary signal highpass filter cut-off frequency
AXMCCMSG BOOL WINAPI MCCMSG_SetPrimarySignalHPF(HMCCMSG hMCCmsg, double dHPF, int *pnError);

// Get primary signal highpass filter cut-off frequency
AXMCCMSG BOOL WINAPI MCCMSG_GetPrimarySignalHPF(HMCCMSG hMCCmsg, double *pdHPF, int *pnError);

//==============================================================================================
// MCC Scope Signal functions
//==============================================================================================

// Set scope signal lowpass filter cut-off frequency
AXMCCMSG BOOL WINAPI MCCMSG_SetScopeSignalLPF(HMCCMSG hMCCmsg, double dLPF, int *pnError);

// Get scope signal lowpass filter cut-off frequency
AXMCCMSG BOOL WINAPI MCCMSG_GetScopeSignalLPF(HMCCMSG hMCCmsg, double *pdLPF, int *pnError);

//==============================================================================================
// MCC Secondary (or Raw) Signal functions
//==============================================================================================

// Set secondary signal
AXMCCMSG BOOL WINAPI MCCMSG_SetSecondarySignal(HMCCMSG hMCCmsg, UINT uSignalID, int *pnError);

// Get secondary signal
AXMCCMSG BOOL WINAPI MCCMSG_GetSecondarySignal(HMCCMSG hMCCmsg, UINT *puSignalID, int *pnError);

// Set secondary signal gain
AXMCCMSG BOOL WINAPI MCCMSG_SetSecondarySignalGain(HMCCMSG hMCCmsg, double dGain, int *pnError);

// Get secondary signal gain
AXMCCMSG BOOL WINAPI MCCMSG_GetSecondarySignalGain(HMCCMSG hMCCmsg, double *pdGain, int *pnError);

// Set secondary signal lowpass filter cut-off frequency
AXMCCMSG BOOL WINAPI MCCMSG_SetSecondarySignalLPF(HMCCMSG hMCCmsg, double dLPF, int *pnError);

// Get secondary signal lowpass filter cut-off frequency
AXMCCMSG BOOL WINAPI MCCMSG_GetSecondarySignalLPF(HMCCMSG hMCCmsg, double *pdLPF, int *pnError);

//==============================================================================================
// MCC Output Zero functions
//==============================================================================================

// Set output zero enable
AXMCCMSG BOOL WINAPI MCCMSG_SetOutputZeroEnable(HMCCMSG hMCCmsg, BOOL bEnable, int *pnError);

// Get output zero enable
AXMCCMSG BOOL WINAPI MCCMSG_GetOutputZeroEnable(HMCCMSG hMCCmsg, BOOL *pbEnable, int *pnError);

// Set output zero amplitude
AXMCCMSG BOOL WINAPI MCCMSG_SetOutputZeroAmplitude(HMCCMSG hMCCmsg, double dAmplitude, int *pnError);

// Get output zero amplitude
AXMCCMSG BOOL WINAPI MCCMSG_GetOutputZeroAmplitude(HMCCMSG hMCCmsg, double *pdAmplitude, int *pnError);

// Execute auto output zero
AXMCCMSG BOOL WINAPI MCCMSG_AutoOutputZero(HMCCMSG hMCCmsg, int *pnError);

//==============================================================================================
// MCC Leak Subtraction functions (VC only)
//==============================================================================================

// Set leak subtraction enable
AXMCCMSG BOOL WINAPI MCCMSG_SetLeakSubEnable(HMCCMSG hMCCmsg, BOOL bEnable, int *pnError);

// Get leak subtraction enable
AXMCCMSG BOOL WINAPI MCCMSG_GetLeakSubEnable(HMCCMSG hMCCmsg, BOOL *pbEnable, int *pnError);

// Set leak subtraction resistance
AXMCCMSG BOOL WINAPI MCCMSG_SetLeakSubResist(HMCCMSG hMCCmsg, double dResistance, int *pnError);

// Get leak subtraction resistance
AXMCCMSG BOOL WINAPI MCCMSG_GetLeakSubResist(HMCCMSG hMCCmsg, double *pdResistance, int *pnError);

// Execute auto leak subtraction
AXMCCMSG BOOL WINAPI MCCMSG_AutoLeakSub(HMCCMSG hMCCmsg, int *pnError);

//==============================================================================================
// MCC Bridge Balance functions (IC only)
//==============================================================================================

// Set bridge balance enable
AXMCCMSG BOOL WINAPI MCCMSG_SetBridgeBalEnable(HMCCMSG hMCCmsg, BOOL bEnable, int *pnError);

// Get bridge balance enable
AXMCCMSG BOOL WINAPI MCCMSG_GetBridgeBalEnable(HMCCMSG hMCCmsg, BOOL *pbEnable, int *pnError);

// Set bridge balance resistance
AXMCCMSG BOOL WINAPI MCCMSG_SetBridgeBalResist(HMCCMSG hMCCmsg, double dResistance, int *pnError);

// Get bridge balance resistance
AXMCCMSG BOOL WINAPI MCCMSG_GetBridgeBalResist(HMCCMSG hMCCmsg, double *pdResistance, int *pnError);

// Execute auto bridge balance
AXMCCMSG BOOL WINAPI MCCMSG_AutoBridgeBal(HMCCMSG hMCCmsg, int *pnError);

//==============================================================================================
// MCC Clear functions (IC only)
//==============================================================================================

// Execute clear +
AXMCCMSG BOOL WINAPI MCCMSG_ClearPlus(HMCCMSG hMCCmsg, int *pnError);

// Execute clear -
AXMCCMSG BOOL WINAPI MCCMSG_ClearMinus(HMCCMSG hMCCmsg, int *pnError);

//==============================================================================================
// MCC Pulse, Zap and Buzz functions
//==============================================================================================

// Execute pulse
AXMCCMSG BOOL WINAPI MCCMSG_Pulse(HMCCMSG hMCCmsg, int *pnError);

// Set pulse amplitude
AXMCCMSG BOOL WINAPI MCCMSG_SetPulseAmplitude(HMCCMSG hMCCmsg, double dAmplitude, int *pnError);

// Get pulse amplitude
AXMCCMSG BOOL WINAPI MCCMSG_GetPulseAmplitude(HMCCMSG hMCCmsg, double *pdAmplitude, int *pnError);

// Set pulse duration
AXMCCMSG BOOL WINAPI MCCMSG_SetPulseDuration(HMCCMSG hMCCmsg, double dDuration, int *pnError);

// Get pulse duration
AXMCCMSG BOOL WINAPI MCCMSG_GetPulseDuration(HMCCMSG hMCCmsg, double *pdDuration, int *pnError);

// Execute zap
AXMCCMSG BOOL WINAPI MCCMSG_Zap(HMCCMSG hMCCmsg, int *pnError);

// Set zap duration
AXMCCMSG BOOL WINAPI MCCMSG_SetZapDuration(HMCCMSG hMCCmsg, double dDuration, int *pnError);

// Get zap duration
AXMCCMSG BOOL WINAPI MCCMSG_GetZapDuration(HMCCMSG hMCCmsg, double *pdDuration, int *pnError);

// Execute buzz
AXMCCMSG BOOL WINAPI MCCMSG_Buzz(HMCCMSG hMCCmsg, int *pnError);

// Set buzz duration
AXMCCMSG BOOL WINAPI MCCMSG_SetBuzzDuration(HMCCMSG hMCCmsg, double dDuration, int *pnError);

// Get buzz duration
AXMCCMSG BOOL WINAPI MCCMSG_GetBuzzDuration(HMCCMSG hMCCmsg, double *pdDuration, int *pnError);

//==============================================================================================
// MCC Meter functions
//==============================================================================================

// Set resistance meter enable
AXMCCMSG BOOL WINAPI MCCMSG_SetMeterResistEnable(HMCCMSG hMCCmsg, BOOL bEnable, int *pnError);

// Get resistance meter enable
AXMCCMSG BOOL WINAPI MCCMSG_GetMeterResistEnable(HMCCMSG hMCCmsg, BOOL *pbEnable, int *pnError);

// Set Irms meter enable
AXMCCMSG BOOL WINAPI MCCMSG_SetMeterIrmsEnable(HMCCMSG hMCCmsg, BOOL bEnable, int *pnError);

// Get Irms meter enable
AXMCCMSG BOOL WINAPI MCCMSG_GetMeterIrmsEnable(HMCCMSG hMCCmsg, BOOL *pbEnable, int *pnError);

// Get the specified meter value in SI units
AXMCCMSG BOOL WINAPI MCCMSG_GetMeterValue(HMCCMSG hMCCmsg, double *pdValue, UINT uMeterID, int *pnError);

//==============================================================================================
// MCC Tool Bar functions
//==============================================================================================

// Execute Reset to Program Defaults
AXMCCMSG BOOL WINAPI MCCMSG_Reset(HMCCMSG hMCCmsg, int *pnError);

// Toggle Always OnTop
AXMCCMSG BOOL WINAPI MCCMSG_ToggleAlwaysOnTop(HMCCMSG hMCCmsg, int *pnError);

// Toggle Resize
AXMCCMSG BOOL WINAPI MCCMSG_ToggleResize(HMCCMSG hMCCmsg, int *pnError);

// Execute Quick Select Buttons
AXMCCMSG BOOL WINAPI MCCMSG_QuickSelectButton(HMCCMSG hMCCmsg, UINT uButtonID, int *pnError);

//==============================================================================================
// Error functions
//==============================================================================================

// Errors etc.
AXMCCMSG BOOL WINAPI MCCMSG_BuildErrorText(HMCCMSG hMCCmsg, int nErrorNum, LPSTR sTxtBuf, UINT uMaxLen);

//==============================================================================================
// Error codes
//==============================================================================================

// General error codes.
const int MCCMSG_ERROR_NOERROR                         = 6000;
const int MCCMSG_ERROR_OUTOFMEMORY                     = 6001;
const int MCCMSG_ERROR_MCCNOTOPEN                      = 6002;
const int MCCMSG_ERROR_INVALIDDLLHANDLE                = 6003;
const int MCCMSG_ERROR_INVALIDPARAMETER                = 6004;
const int MCCMSG_ERROR_MSGTIMEOUT                      = 6005;
const int MCCMSG_ERROR_MCCCOMMANDFAIL                  = 6006;

//==============================================================================================
// Function parameters
//==============================================================================================

// Parameters for MCCMSG_FindFirstMultiClamp(), MCCMSG_FindNextMultiClamp() and MCCMSG_SelectMultiClamp()
// uModel filled in / or puModel filled out as:
const int MCCMSG_HW_TYPE_MC700A                         = 0;
const int MCCMSG_HW_TYPE_MC700B                         = 1;

// Parameters for MCCMSG_SetMode() and MCCMSG_GetMode()
// uModeID filled in / or puModeID filled out as:
const UINT MCCMSG_MODE_VCLAMP                           = 0;
const UINT MCCMSG_MODE_ICLAMP                           = 1;   
const UINT MCCMSG_MODE_ICLAMPZERO                       = 2;

// Parameters for MCCMSG_QuickSelectButton()
// uButtonID filled in as:
const UINT MCCMSG_QSB_1                                 = 0;
const UINT MCCMSG_QSB_2                                 = 1;
const UINT MCCMSG_QSB_3                                 = 2;

// Parameters for MCCMSG_SetPrimarySignal(), MCCMSG_SetPrimarySignal()
// uSignalID filled in / or puSignalID filled out as:
const UINT MCCMSG_PRI_SIGNAL_VC_MEMBCURRENT             = 0;  // 700B and 700A 
const UINT MCCMSG_PRI_SIGNAL_VC_MEMBPOTENTIAL           = 1;  // 700B and 700A
const UINT MCCMSG_PRI_SIGNAL_VC_PIPPOTENTIAL            = 2;  // 700B and 700A
const UINT MCCMSG_PRI_SIGNAL_VC_100XACMEMBPOTENTIAL     = 3;  // 700B and 700A
const UINT MCCMSG_PRI_SIGNAL_VC_EXTCMDPOTENTIAL         = 4;  // 700B only
const UINT MCCMSG_PRI_SIGNAL_VC_AUXILIARY1              = 5;  // 700B and 700A
const UINT MCCMSG_PRI_SIGNAL_VC_AUXILIARY2              = 6;  // 700B only

const UINT MCCMSG_PRI_SIGNAL_IC_MEMBPOTENTIAL           = 7;  // 700B and 700A
const UINT MCCMSG_PRI_SIGNAL_IC_MEMBCURRENT             = 8;  // 700B and 700A
const UINT MCCMSG_PRI_SIGNAL_IC_CMDCURRENT              = 9;  // 700B and 700A
const UINT MCCMSG_PRI_SIGNAL_IC_100XACMEMBPOTENTIAL     = 10; // 700B and 700A
const UINT MCCMSG_PRI_SIGNAL_IC_EXTCMDCURRENT           = 11; // 700B only
const UINT MCCMSG_PRI_SIGNAL_IC_AUXILIARY1              = 12; // 700B and 700A
const UINT MCCMSG_PRI_SIGNAL_IC_AUXILIARY2              = 13; // 700B only

// Parameters for MCCMSG_SetSecondarySignal(), MCCMSG_SetSecondarySignal()
// uSignalID filled in / or puSignalID filled out as:
const UINT MCCMSG_SEC_SIGNAL_VC_MEMBCURRENT             = 0;  // 700B and 700A
const UINT MCCMSG_SEC_SIGNAL_VC_MEMBPOTENTIAL           = 1;  // 700B and 700A
const UINT MCCMSG_SEC_SIGNAL_VC_PIPPOTENTIAL            = 2;  // 700B and 700A
const UINT MCCMSG_SEC_SIGNAL_VC_100XACMEMBPOTENTIAL     = 3;  // 700B and 700A
const UINT MCCMSG_SEC_SIGNAL_VC_EXTCMDPOTENTIAL         = 4;  // 700B only
const UINT MCCMSG_SEC_SIGNAL_VC_AUXILIARY1              = 5;  // 700B and 700A
const UINT MCCMSG_SEC_SIGNAL_VC_AUXILIARY2              = 6;  // 700B only

const UINT MCCMSG_SEC_SIGNAL_IC_MEMBPOTENTIAL           = 7;  // 700B and 700A
const UINT MCCMSG_SEC_SIGNAL_IC_MEMBCURRENT             = 8;  // 700B and 700A
const UINT MCCMSG_SEC_SIGNAL_IC_CMDCURRENT              = 9;  //          700A only
const UINT MCCMSG_SEC_SIGNAL_IC_PIPPOTENTIAL            = 10; // 700B only
const UINT MCCMSG_SEC_SIGNAL_IC_100XACMEMBPOTENTIAL     = 11; // 700B and 700A
const UINT MCCMSG_SEC_SIGNAL_IC_EXTCMDCURRENT           = 12; // 700B only
const UINT MCCMSG_SEC_SIGNAL_IC_AUXILIARY1              = 13; // 700B and 700A
const UINT MCCMSG_SEC_SIGNAL_IC_AUXILIARY2              = 14; // 700B only

// Parameters for MCCMSG_GetMeterValue()
const UINT MCCMSG_METER1                                = 0;  // 700B 
const UINT MCCMSG_METER2                                = 1;  // 700B 
const UINT MCCMSG_METER3                                = 2;  // 700B 
const UINT MCCMSG_METER4                                = 3;  // 700B 

//==============================================================================================
// Constants
//==============================================================================================

const UINT MCCMSG_TIMEOUT_DEFAULT                       = 3000; // default time out (3 sec).
const UINT MCCMSG_SERIALNUM_SIZE                        = 16;

} // end of extern "C"

#endif // INC_AXMULTICLAMPMSG_HPP