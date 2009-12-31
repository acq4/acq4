/* C-style comment */
// C++ style comment

#define MACRO1 macro1
#define MACRO2 "string macro"
  
#ifdef MACRO1
  //#define MACRO3 commentedMacro3
  #define MACRO4 macro4 /*with comment*/
#endif

#ifdef UNDEFINED
  #define NO_DEFINE
  int NO_DECLARE;
#endif

#ifndef DEFINE3
  #define DEFINE3 10
  #ifndef DEFINE3
    #define NO_DEFINE2
    int NO_DECLARE2;
  #endif
#endif

#define MARKER1
#if !defined DEFINE3
  #define NO_DEFINE3
  int NO_DECLARE3;
  #ifdef DEFINE3
    #define NO_DEFINE6
  #endif
#else
  #define DEFINE4
#endif


#define mlm Multi Line\
            Macro

#if defined DEFINE4 && DEFINE3 < 5
  #define NO_DEFINE4
  int NO_DECLARE4;
#elif defined DEFINE4 && DEFINE3 > 5
  #define DEFINE5
  int DECLARE5;
#else
  #define NO_DEFINE6
  int NO_DECLARE6;
#endif



int MACRO1;
char* str1 = "normal string";
char** str2 = "string with macro: MACRO1";
static const char* const str3 = "string with comment: /*comment inside string*/";
/*char* str4 = "string inside comment"*/
int str5[2] = {0x1, 3.1415e6};
/*char* str5 = "commented string with \"escaped quotes\" "*/
char* str6 = "string with define #define MACRO5 macro5_in_string ";
char* str7 = "string with \"escaped quotes\" ";
static const int * const (**intJunk[4]);
int(*fnPtr)(char, float);

int x1 = (5 + 3 * 0x1) / 8.0;
int x2 = (typeCast)0x544 <<16;


/* comment */ int betweenComments /* comment */ ;

#define MACRO5
typedef char **typeChar;
typedef int typeInt, *typeIntPtr, typeIntArr[10], typeIntDArr[5][5];
typedef typeInt typeTypeInt;
typedef unsigned long ULONG;

typeTypeInt *ttip5[5];

struct structName 
{
  int x; typeTypeInt y;
  char str[10] = "brace }  \0"; /* commented brace } */
} structInst; 

typedef struct structName *structNamePtr;

typedef struct structName2 {
    int x;
    int y;
} *structName2Ptr;

typedef union unionName {
    int x;
    int y;
} *unionNamePtr;

typedef struct { int x; } *anonStructPtr;

struct recursiveStruct {
    struct recursiveStruct *next;
};

static const int constVar = 5;

enum enumName
{
    enum1=2,
    enum2=0, enum3,
    enum4
}  enumInst;


int __declspec(dllexport) __stdcall function1();
int *function2(typeInt x);
typeTypeInt ** function3(int x, int y)
{
     JUNK
     { }
     int localVariable = 1;
}

// undefined types
typedef someType SomeOtherType;
undefined x;

// recursive type definitions
typedef recType1 recType2;
typedef recType2 recType3;
typedef recType3 recType1;

#define NEAR near
typedef struct tagWNDCLASSEXA {
    int         cbClsExtra;
    int         cbWndExtra;
} WNDCLASSEXA, *PWNDCLASSEXA, NEAR *NPWNDCLASSEXA;//, FAR *LPWNDCLASSEXA;
