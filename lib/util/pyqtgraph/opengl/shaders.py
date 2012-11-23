from OpenGL.GL import *
from OpenGL.GL import shaders

## For centralizing and managing vertex/fragment shader programs.

def initShaders():
    global Shaders
    Shaders = [
        ShaderProgram(None, []),
        ShaderProgram('balloon', [   ## increases fragment alpha as the normal turns orthogonal to the view
            VertexShader("""
                varying vec3 normal;
                void main() {
                    // compute here for use in fragment shader
                    normal = normalize(gl_NormalMatrix * gl_Normal);
                    gl_FrontColor = gl_Color;
                    gl_BackColor = gl_Color;
                    gl_Position = ftransform();
                }
            """),
            FragmentShader("""
                varying vec3 normal;
                void main() {
                    vec4 color = gl_Color;
                    color.w = min(color.w + 2.0 * color.w * pow(normal.x*normal.x + normal.y*normal.y, 5.0), 1.0);
                    gl_FragColor = color;
                }
            """)
        ]),
        ShaderProgram('viewNormalColor', [   ## colors fragments based on face normals relative to view
            VertexShader("""
                varying vec3 normal;
                void main() {
                    // compute here for use in fragment shader
                    normal = normalize(gl_NormalMatrix * gl_Normal);
                    gl_FrontColor = gl_Color;
                    gl_BackColor = gl_Color;
                    gl_Position = ftransform();
                }
            """),
            FragmentShader("""
                varying vec3 normal;
                void main() {
                    vec4 color = gl_Color;
                    color.x = (normal.x + 1) * 0.5;
                    color.y = (normal.y + 1) * 0.5;
                    color.z = (normal.z + 1) * 0.5;
                    gl_FragColor = color;
                }
            """)
        ]),
        ShaderProgram('normalColor', [   ## colors fragments based on absolute face normals
            VertexShader("""
                varying vec3 normal;
                void main() {
                    // compute here for use in fragment shader
                    normal = normalize(gl_Normal);
                    gl_FrontColor = gl_Color;
                    gl_BackColor = gl_Color;
                    gl_Position = ftransform();
                }
            """),
            FragmentShader("""
                varying vec3 normal;
                void main() {
                    vec4 color = gl_Color;
                    color.x = (normal.x + 1) * 0.5;
                    color.y = (normal.y + 1) * 0.5;
                    color.z = (normal.z + 1) * 0.5;
                    gl_FragColor = color;
                }
            """)
        ]),
        ShaderProgram('shaded', [   ## very simple simulation of lighting
            VertexShader("""
                varying vec3 normal;
                void main() {
                    // compute here for use in fragment shader
                    normal = normalize(gl_NormalMatrix * gl_Normal);
                    gl_FrontColor = gl_Color;
                    gl_BackColor = gl_Color;
                    gl_Position = ftransform();
                }
            """),
            FragmentShader("""
                varying vec3 normal;
                void main() {
                    float p = dot(normal, normalize(vec3(1, -1, -1)));
                    p = p < 0. ? 0. : p * 0.8;
                    vec4 color = gl_Color;
                    color.x = color.x * (0.2 + p);
                    color.y = color.y * (0.2 + p);
                    color.z = color.z * (0.2 + p);
                    gl_FragColor = color;
                }
            """)
        ]),
        ShaderProgram('edgeHilight', [   ## colors get brighter near edges of object
            VertexShader("""
                varying vec3 normal;
                void main() {
                    // compute here for use in fragment shader
                    normal = normalize(gl_NormalMatrix * gl_Normal);
                    gl_FrontColor = gl_Color;
                    gl_BackColor = gl_Color;
                    gl_Position = ftransform();
                }
            """),
            FragmentShader("""
                varying vec3 normal;
                void main() {
                    vec4 color = gl_Color;
                    float s = pow(normal.x*normal.x + normal.y*normal.y, 2.0);
                    color.x = color.x + s * (1.0-color.x);
                    color.y = color.y + s * (1.0-color.y);
                    color.z = color.z + s * (1.0-color.z);
                    gl_FragColor = color;
                }
            """)
        ]),
        ShaderProgram('pointSprite', [   ## allows specifying point size using normal.x
            ## See:
            ##
            ##  http://stackoverflow.com/questions/9609423/applying-part-of-a-texture-sprite-sheet-texture-map-to-a-point-sprite-in-ios
            ##  http://stackoverflow.com/questions/3497068/textured-points-in-opengl-es-2-0
            ##
            ##
            VertexShader("""
                void main() {
                    gl_FrontColor=gl_Color;
                    gl_PointSize = gl_Normal.x;
                    gl_Position = ftransform();
                } 
            """),
            #FragmentShader("""
                ##version 120
                #uniform sampler2D texture;
                #void main ( )
                #{
                    #gl_FragColor = texture2D(texture, gl_PointCoord) * gl_Color;
                #}
            #""")
        ]),
    ]


CompiledShaderPrograms = {}
    
def getShaderProgram(name):
    return ShaderProgram.names[name]

class VertexShader:
    def __init__(self, code):
        self.code = code
        self.compiled = None
        
    def shader(self):
        if self.compiled is None:
            self.compiled = shaders.compileShader(self.code, GL_VERTEX_SHADER)
        return self.compiled

class FragmentShader:
    def __init__(self, code):
        self.code = code
        self.compiled = None
        
    def shader(self):
        if self.compiled is None:
            self.compiled = shaders.compileShader(self.code, GL_FRAGMENT_SHADER)
        return self.compiled
        
        

class ShaderProgram:
    names = {}
    
    def __init__(self, name, shaders):
        self.name = name
        ShaderProgram.names[name] = self
        self.shaders = shaders
        self.prog = None

    def program(self):
        if self.prog is None:
            compiled = [s.shader() for s in self.shaders]  ## compile all shaders
            self.prog = shaders.compileProgram(*compiled)  ## compile program
        return self.prog
        
    def __enter__(self):
        if len(self.shaders) > 0:
            glUseProgram(self.program())
        
    def __exit__(self, *args):
        if len(self.shaders) > 0:
            glUseProgram(0)
        
    def uniform(self, name):
        """Return the location integer for a uniform variable in this program"""
        return glGetUniformLocation(self.program(), name)

        
initShaders()