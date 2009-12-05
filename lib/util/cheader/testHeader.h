/* C-style comment */
// C++ style comment

#define MACRO1 macro1
  #define MACRO2 2
#ifdef MACRO1
//#define MACRO3 commentedMacro3
#define MACRO4 macro4 /*with comment*/
#endif

int MACRO1;
char* str1 = "normal string";
char** str2 = "string with macro: MACRO1";
static const char* const str3 = "string with comment: /*comment inside string*/";
/*char* str4 = "string inside comment"*/
int str5[2] = {0x1, 3.1415e6};
/*char* str5 = "commented string with \"escaped quotes\" "*/
char* str6 = "string with define #define MACRO5 macro5 ";
char* str7 = "string with \"escaped quotes\" ";

/* comment */ int betweenComments /* comment */ ;

typedef char **typeChar;
typedef int typeInt, *typeIntPtr, typeIntArr[10], typeIntDArr[5][5];
typedef typeInt typeTypeInt;

struct structName 
{
  int x; typeTypeInt y;
  char str[10] = "brace }  \0"; /* commented brace } */
} structInst; 

static const int constVar = 5;

enum enumName
{
    enum1=2,
    enum2=0, enum3,
    enum4
}  enumInst;


int function1();
int *function2(typeInt x);
typeTypeInt ** function3(int x, int y)
{
     JUNK
     { }
     int localVariable = 1;
}