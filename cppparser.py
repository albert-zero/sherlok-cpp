# -*- coding: utf-8 -*-
"""
    CppParser: 
    Instruments C/CPP files for using together with sherlok
    
    Copyright (C) 2015  Albert Zedlitz

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
 
"""

import sys
import os
import re
import shutil
from   optparse import OptionParser

__all__     = []
__version__ = 0.1
__date__    = '2016-07-08'
__updated__ = '2016-07-08'

DEBUG   = 0
TESTRUN = 0
PROFILE = 0

# ------------------------------------------------------------------------------------
# ------------------------------------------------------------------------------------
class TranslateException (Exception):
    def __init__(self):
        super()
    
# ------------------------------------------------------------------------------------
# ------------------------------------------------------------------------------------
class TBlock:
    """ TBlock is the description of a block element, typically starting/ending with curly
    brackets. There are some distinct type of block, which are handled individually 
    """
    STATEMENT   = 0
    CLASS       = 1
    METHOD      = 2
    FUNCTION    = 3
    TEMPLATE    = 4
    DECLARATION = 5
    MACRO       = 6
    gEnumNames  = ['STATEMENT', 'CLASS', 'METHOD', 'FUNC', 'TEMPL', 'DECL', 'MACRO']
    
    # --------------------------------------------------------------------------------
    # --------------------------------------------------------------------------------            
    def __init__(self, aType, aDescr = "", aBlockEnv=None):
        """ Initializes a block.
        """
        self.mListToken  = list()
        self.mListArgs   = list()
        self.mBlockType  = aType
        self.mBlockEnv   = aBlockEnv
        self.mNested     = None
        self.mClassName  = aDescr
        
        self.mArguments  = None
        self.mMacroBlock = str()
        self.mName       = aDescr
        
        self.mProcessing = True
        self.mDone       = False
        self.mSkipNested = False
        
        if not self.mBlockEnv:
            self.mBlockEnv = self
                    
        
    # --------------------------------------------------------------------------------
    # --------------------------------------------------------------------------------
    def conditionalBlock(self, aDoProcess):
        """  The default processing state is True. A conditional block could be switch 
        switched on for exactly one. Once called with aDoProcess=True the block could 
        only be disabled in further calls. 
        """
        if aDoProcess and not self.mDone:
            self.mDone       = True
            self.mProcessing = True
        else:
            self.mProcessing = False
            
    # --------------------------------------------------------------------------------
    # --------------------------------------------------------------------------------        
    def doProcess(self):
        """ Return the block processing state """
        return self.mProcessing
    
        
# ------------------------------------------------------------------------------------
# ------------------------------------------------------------------------------------
class TParser:
    """ Reads files from an input directory and injects sherlok statements """
    # --------------------------------------------------------------------------------
    # --------------------------------------------------------------------------------            
    def __init__(self, aInFile, aSherlokSrc):
        """ aInFile could be a directory or single file 
        aOutFile is a directory """
        self.mInFile       = aInFile
        self.mSherlokSrc   = aSherlokSrc
        self.mBlockList    = list()
        self.mDefines      = ['SAPonNT']
        self.mUndefines    = ['NATIVE_BEGIN', 'NATIVE_END', 'TRY_MAIN', 'EXCEPT_MAIN']
        self.mLine         = 0
        self.mPackage      = str()
        self.mClass        = str()
        
        self.mSkipNext     = False
        self.mSkipAll      = False
        
    # --------------------------------------------------------------------------------
    # --------------------------------------------------------------------------------            
    def translateProject(self):
        """ Translate all files from input directory """ 
        xProjectRoot = str()
        
        if os.path.isdir(self.mInFile):
            xGenDir      = os.walk(self.mInFile)
            xDirEntry    = xGenDir.__next__()
            xProjectRoot = xDirEntry[0]
            
            for xFile in xDirEntry[2]:
                xFqFileName = os.path.join(xDirEntry[0], xFile)
                self.translateOneFile(xFqFileName)
            
        else:
            xProjectRoot = os.path.split(self.mInFile)[0]
            self.translateOneFile(self.mInFile)

        if not xProjectRoot:
            xProjectRoot = '.'
        
        if os.path.exists( os.path.join(self.mSherlokSrc, 'cti.h') ):
            shutil.copy( os.path.join(self.mSherlokSrc, 'cti.h'), xProjectRoot ) 
            
        if os.path.exists( os.path.join(self.mSherlokSrc, 'cti.cpp') ):
            shutil.copy( os.path.join(self.mSherlokSrc, 'cti.cpp'), xProjectRoot ) 
            
            
    # --------------------------------------------------------------------------------
    # --------------------------------------------------------------------------------            
    def translateOneFile(self, aFqFileName):
        xAlreadyTranslated = False
        
        xExtension = os.path.splitext(aFqFileName)
        if xExtension[-1] not in ['.c', '.cpp', '.h', '.hpp']:
            return
        
        with open(aFqFileName,  "r") as xInFile:
            xBuffer  = xInFile.readline()
            # Already translated file: Reset and try again
            if 'cti.h' in xBuffer:
                xAlreadyTranslated = True
        
        if xAlreadyTranslated:
            try:
                os.replace(aFqFileName + '.orig', aFqFileName)  
            except Exception as xEx:
                raise
            
        xFqFileTmp     =  aFqFileName + '.sherlok'    
        xDir,  xFile   = os.path.split(aFqFileName)
        xBase, xExt    = os.path.splitext(xFile)

        self.mPackage  = xDir.split(os.sep + 'src' + os.sep)[-1].replace(os.sep, '.')
        self.mClass    = xBase
        
        print('translate {}'.format(aFqFileName))

        try:            
            with open(aFqFileName,  "r") as xInFile:
                with open(xFqFileTmp, "w") as xOutFile:
                    self.translate(xInFile, xOutFile)
                        
            os.rename(aFqFileName, aFqFileName + '.orig')
            os.rename(xFqFileTmp,  aFqFileName)                        
        except Exception as xEx:
            print ('{}: file {}:{}'.format(xEx, aFqFileName, self.mLine))
            raise

    # --------------------------------------------------------------------------------
    # --------------------------------------------------------------------------------            
    def translate(self, aInFile, aOutFile):
        xTokenList      = list()
        xLastToken      = ''     # Used to sync parser after reading a new block
        xReadBlock      = None   # Contains the end sequence of a block
        
        xSkipNextToken  = False  # Skip token for method/function argument list
        xQualifier      = str()  # Store qualifier * or & for an argument
        xBuffer         = str()        
        self.mBlockList = list()
        
        xBlock          = TBlock(TBlock.DECLARATION, self.mClass)
        self.mBlockList.append(xBlock)
                
        self.mLine      = 0        
        aOutFile.write('#include "cti.h"\n')
        
        for xBuffer in aInFile:
            self.mLine += 1

            if xLastToken:
                xBuffer    = xLastToken + xBuffer
                xLastToken = None

            xBufferLen = len(xBuffer)
            xIndex     = 0
            xInxFind   = 0
            
            while xIndex < xBufferLen:                 
                # Read block. 
                # If the block happens to exceed the buffer: 
                # read a new chunk, restore the last token and continue
                if xReadBlock:
                    if xIndex + len(xReadBlock) > xBufferLen:
                        xLastToken = xBlock[xIndex:]
                        break
                    
                    xInxFind = xBuffer.find(xReadBlock, xInxFind)
                    if xInxFind < 0:
                        aOutFile.write(xBuffer[xIndex:])
                        xLastToken = xBuffer[-1]
                        break

                    if xBuffer[xInxFind-1] == '\\':
                        if xBuffer[xInxFind-2] != '\\':
                            xInxFind += 1
                            continue
                    
                    if xBuffer[xIndex:xInxFind]   == '/*CCQ_SHERLOK_SKIP_FCTN*/':
                        self.mSkipNext = True                    
                    elif xBuffer[xIndex:xInxFind] == '/*CCQ_SHERLOK_SKIP_FILE*/':
                        self.mSkipAll  = True
                    
                    xInxFind += len(xReadBlock)
                                        
                    # Evaluate the macro blocks according to preprocessor statements. 
                    # This is necessary for counting the brackets correctly
                    while xBuffer[xIndex] == '#':                        
                        xMacroStmt  = xBuffer[xIndex:xInxFind]

                        if re.search('#\W*endif', xMacroStmt):
                            xBlock = self.mBlockList.pop()
                            break

                        # inherit processing and environment
                        # Macro blocks are nested independent from program logic
                        for xBlockEnv in reversed(self.mBlockList):
                            if xBlockEnv != TBlock.MACRO:
                                break
                            
                        xProcess  = self.mBlockList[-1].doProcess()
                                                            
                        xMacroBlock = re.search('#\W*if\W*(defined)\W*(\w+)', xMacroStmt)
                        if xMacroBlock:
                            xBlock = TBlock( TBlock.MACRO, xMacroBlock.group(2), xBlockEnv )
                            xBlock.conditionalBlock( xProcess and (xMacroBlock.group(2) in self.mDefines ))
                            self.mBlockList.append(xBlock)
                            break
                        
                        xMacroBlock = re.search('#\W*(ifdef)\W*(\w+)',  xMacroStmt)
                        if xMacroBlock:
                            xBlock = TBlock( TBlock.MACRO, xMacroBlock.group(2), xBlockEnv )
                            xBlock.conditionalBlock( xProcess and (xMacroBlock.group(2) in self.mDefines ))
                            self.mBlockList.append(xBlock)
                            break
                        
                        xMacroBlock = re.search('#\W*(ifndef)\W*(\w+)', xMacroStmt)
                        if xMacroBlock:
                            xBlock = TBlock( TBlock.MACRO, xMacroBlock.group(2), xBlockEnv )
                            xBlock.conditionalBlock( xProcess and (xMacroBlock.group(2) not in self.mDefines ))
                            self.mBlockList.append(xBlock)
                            break
                        
                        xMacroBlock = re.search('#\W*(if)\W*(\w+)', xMacroStmt)
                        if xMacroBlock:
                            xBlock = TBlock(TBlock.MACRO, "", xBlockEnv )
                            xBlock.conditionalBlock( xProcess and (xMacroBlock.group(2) in '1' ))
                            self.mBlockList.append(xBlock)
                            break
                                
                        xBlock      = self.mBlockList[-1]
                        xMacroBlock = re.search('(#\W*elif )(\w+)', xMacroStmt)
                        if xMacroBlock:
                            xCondition = xMacroBlock.group(2) in self.mDefines
                            xBlock.conditionalBlock( xCondition )
                            break
                        
                        if re.search('#\W*else', xMacroStmt):
                            xBlock.conditionalBlock(True)
                            break
                                                
                        xMacroBlock = re.search('(#\W*define\W*)(\w+)', xMacroStmt)
                        if xMacroBlock:
                            if xBlock.doProcess():
                                self.mDefines.append( xMacroBlock.group(2) )
                            break
                        break
                    
                    aOutFile.write(xBuffer[xIndex:xInxFind])
                    xReadBlock = None
                    xIndex     = xInxFind
                    continue
                
                # Read next char and set xInxFind for block processing (xReadBlock != None)
                xNextChar = xBuffer[xIndex]
                xInxFind  = xIndex + 1

                # Read macro
                if xNextChar == '#':
                    xReadBlock  = '\n'
                    continue
                                
                # Read comments as block. 
                if xNextChar == '/':
                    try:
                        if xBuffer[xIndex+1] == '/':
                            xReadBlock = '\n'
                            xInxFind  += 1
                            continue
                        elif xBuffer[xIndex+1] == '*':
                            xReadBlock = '*/'
                            xInxFind  += 1
                            continue
                    except IndexError as xEx:
                        xLastToken = '/'
                        break                
                
                # Read strings as block
                if xNextChar == '"':
                    xReadBlock = '"'
                    continue

                if xNextChar == "'":
                    xReadBlock = "'"
                    continue

                # Check if this block needs to be processed
                if not self.mBlockList[-1].doProcess():
                    aOutFile.write(xNextChar)
                    xIndex += 1
                    continue

                # Read tokens. If the token is at the end of the buffer, store the value
                # and read the next chunk
                if xNextChar.isalnum() or xNextChar in ['~', '_']:
                    try:                        
                        xResult    = re.search('[~]?\w+', xBuffer[xIndex:])
                        xLastToken = xResult.group(0)
                        xInxFind   = xResult.span(0)[1] + xIndex
                    except IndexError as xEx:
                        break;
                    
                    if xLastToken not in self.mUndefines:
                        aOutFile.write(xBuffer[xIndex:xInxFind])
                    else:
                        xMatch = re.search('\([\w ,]*\)', xBuffer[xIndex:])
                        if xMatch:
                            xIndex += xMatch.span(0)[1]
                            xLastToken = None
                        else:
                            xIndex = xInxFind
                        continue    
                        
                    if 'class' in xTokenList:
                        xBlock = self.mBlockList[-1]
                        xBlock.mNested  = TBlock(TBlock.CLASS, xLastToken)
                        xTokenList = list()
                    
                    if xSkipNextToken:
                        xSkipNextToken = False
                    else:    
                        xTokenList.append(xLastToken)
                    xIndex     = xInxFind
                    xLastToken = None
                    continue
                
                if xNextChar == '{':
                    xBlock = self.mBlockList[-1]
                                                                
                    if xBlock.mNested:
                        # print('block {} {} {}'.format( TBlock.gEnumNames[xBlock.mNested.mBlockType], xBlock.mNested.mName, xBlock.mNested.mListArgs))                            
                        self.mBlockList.append(xBlock.mNested)
                        
                        if xBlock.mNested.mBlockType in [TBlock.METHOD, TBlock.FUNCTION]:                            
                            xMethodName = xBlock.mNested.mName
                            xClassName  = xBlock.mNested.mClassName
                            xSignature  = str()
                            xArgsList   = str()
                                                        
                            if xBlock.mNested.mListArgs:
                                xSignature  = ','.join(xBlock.mNested.mListArgs)
                                xArgsList   = [x.split(':')[0] for x in xBlock.mNested.mListArgs]

                            if self.mSkipNext or self.mSkipAll:
                                xBlock.mNested.mBlockType = TBlock.STATEMENT
                                self.mSkipNext = False
                            elif xMethodName == 'mainU':
                                xArgsList[0] = '&' + xArgsList[0] 
                                aOutFile.write('CCQ_SHERLOK_BEGIN( cR("{}"), cR("{}"), {}, {} )'.format(self.mPackage, xClassName, *xArgsList))
                                xNextChar = ''
                            else:
                                if len(xArgsList) > 0:
                                    aOutFile.write('CCQ_SHERLOK_FCT_BEGIN( cR("{}"), cR("{}"), cR("{}"), cR("{}"), {} )'.format(self.mPackage, xClassName, xMethodName, xSignature, ','.join(xArgsList)))
                                else:
                                    aOutFile.write('CCQ_SHERLOK_FCT_BEGIN( cR("{}"), cR("{}"), cR("{}"), cR("{}") )'.format(self.mPackage, xClassName, xMethodName, xSignature))
                                    
                                xNextChar = ''
                        xBlock.mNested = None
                    else:
                        self.mBlockList.append( TBlock(TBlock.STATEMENT) )
                        
                        
                elif xNextChar == '}':
                    xBlock = self.mBlockList.pop()
                    if xBlock.mBlockType in [TBlock.METHOD, TBlock.FUNCTION]:
                        xNextChar = ''
                    
                        if xBlock.mName == 'mainU':  
                            aOutFile.write('CCQ_SHERLOK_END\n')
                            aOutFile.write('#include "cti.cpp"')                            
                        else:
                            aOutFile.write('CCQ_SHERLOK_FCT_END')

                elif xNextChar == '=':
                    xBlock = self.mBlockList[-1]
                    if xBlock.mNested:
                        if xBlock.mNested.mArguments != None:
                            xSkipNextToken = True
                    else:
                        xBlock.mNested = TBlock(TBlock.STATEMENT)
                        
                elif xNextChar in ['*']:
                    xBlock = self.mBlockList[-1]
                    if xBlock.mNested and xBlock.mNested.mArguments != None:
                        xQualifier += xNextChar

                elif xNextChar in [':']:
                    xQualifier += ':'
                    
                elif xNextChar == '[':
                    xBlock = self.mBlockList[-1]
                    if xBlock.mNested and xBlock.mNested.mArguments != None:
                        xQualifier += '*'

                elif xNextChar == ';':
                    self.mBlockList[-1].mNested = None
                
                # This could be a function or method declaration
                # Create a nested temporary block and wait for "};" to create or discard
                elif xNextChar == '(':
                    xBlock = self.mBlockList[-1]
                    
                    if xBlock.mNested == None:
                        if xBlock.mBlockEnv.mBlockType == TBlock.DECLARATION:
                            if xQualifier == '::':
                                xBlock.mNested = TBlock(TBlock.METHOD, xTokenList[-1])
                                xBlock.mNested.mClassName = xTokenList[-2]
                            else:
                                xBlock.mNested = TBlock(TBlock.FUNCTION, xTokenList[-1])
                                xBlock.mNested.mClassName = xBlock.mBlockEnv.mName
                            xBlock.mNested.mArguments = list()
                        elif xBlock.mBlockEnv.mBlockType == TBlock.CLASS:
                            xBlock.mNested = TBlock(TBlock.METHOD, xTokenList[-1])
                            xBlock.mNested.mClassName = xBlock.mBlockEnv.mName
                            xBlock.mNested.mArguments = list()
                        else:
                            xBlock.mNested = TBlock(TBlock.STATEMENT)
                    xTokenList = list()
                    xQualifier = str()
                    
                # This could be an argument-list of a method/function
                # In this case mNested and mNested.mArguments are defined
                elif xNextChar in [')', ',']:
                    xSkipNextToken = False
                    xBlock         = self.mBlockList[-1]
                    
                    if xBlock.mNested:
                        if xBlock.mNested.mBlockType in [TBlock.METHOD, TBlock.FUNCTION]:
                            if len(xTokenList) > 1 and xBlock.mNested.mArguments != None:
                                xBlock.mNested.mArguments.append( '{}:{}'.format(xTokenList[-1], xTokenList[-2]+xQualifier) )
                        else:
                            xBlock.mNested = None
                            
                        if xNextChar == ')':
                            if xBlock.mNested != None and xBlock.mNested.mArguments != None:
                                xBlock.mNested.mListArgs  = xBlock.mNested.mArguments
                                xBlock.mNested.mArguments = None

                        xQualifier = str()
                        xTokenList = list()
                    
                aOutFile.write(xNextChar)
                xIndex += 1        
                                   
    
# --------------------------------------------------------------------------------
# --------------------------------------------------------------------------------            
def main(argv=None):
    '''Command line options.'''

    program_name = os.path.basename(sys.argv[0])
    program_version    = "v0.1"
    program_build_date = "%s" % __updated__

    program_version_string = '%%prog %s (%s)' % (program_version, program_build_date)
    #program_usage = '''usage: spam two eggs''' # optional - will be autogenerated by optparse
    program_longdesc = '''''' # optional - give further explanation about what the program does
    program_license = "Copyright 2016 user_name (organization_name)                                            \
                Licensed under the Apache License 2.0\nhttp://www.apache.org/licenses/LICENSE-2.0"

    if argv is None:
        argv = sys.argv[1:]
    try:
        # setup option parser
        parser = OptionParser(version=program_version_string, epilog=program_longdesc, description=program_license)
        parser.add_option("-i", "--in",       dest="infile",  help="set input path [default: %default]")
        parser.add_option("-s", "--sherlok",  dest="sherlok", help="set sherlok development path [default: %default]")
        parser.add_option("-v", "--verbose",  dest="verbose", action="count", help="set verbosity level [default: %default]")

        # set defaults
        parser.set_defaults(infile=".", sherlok=".")

        # process options
        (opts, args) = parser.parse_args(argv)

        #if opts.verbose > 0:
        #    print("verbosity level = %d" % opts.verbose)
        if opts.infile:
            print("infile  = {}".format(opts.infile))
        if opts.sherlok:
            print("sherlok = {}".format(opts.sherlok))

        # MAIN BODY #
        aParser = TParser(opts.infile, opts.sherlok);
        aParser.translateProject()
        
    except Exception as e:
        indent = len(program_name) * " "
        sys.stderr.write(program_name + ": " + repr(e) + "\n")
        sys.stderr.write(indent + "  for help use --help")
        raise


# --------------------------------------------------------------------------------
# --------------------------------------------------------------------------------            
if __name__ == "__main__":
    if DEBUG:
        sys.argv.append("-h")
    if TESTRUN:
        import doctest
        doctest.testmod()
    if PROFILE:
        import cProfile
        import pstats
        profile_filename = 'cppparser_profile.txt'
        cProfile.run('main()', profile_filename)
        statsfile = open("profile_stats.txt", "wb")
        p = pstats.Stats(profile_filename, stream=statsfile)
        stats = p.strip_dirs().sort_stats('cumulative')
        stats.print_stats()
        statsfile.close()
        sys.exit(0)
    sys.exit(main())
    
    