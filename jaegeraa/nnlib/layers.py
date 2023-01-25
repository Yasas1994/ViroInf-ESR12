import tensorflow as tf
import tensorflow.keras as keras
from tensorflow.keras.layers import InputSpec
import tensorflow.keras.backend as K
import numpy as np

class HighWay(keras.layers.Layer):
    def __init__(self, units=32, input_dim=32, weights_initializer=None):
        super(HighWay, self).__init__()
        
        if weights_initializer:
            w_init = weights_initializer
        else:
            w_init = tf.random_normal_initializer()
        
        b_init = tf.zeros_initializer()
        
        self.w = tf.Variable(
            initial_value=w_init(shape=(input_dim, units), dtype="float32"),
            trainable=True,
        )
        #t gate
        #c gate == 1 - t
        self.t = tf.Variable(
            initial_value=w_init(shape=(input_dim, units), dtype="float32"),
            trainable=True,
        )
        
        self.b = tf.Variable(
            initial_value=b_init(shape=(units,), dtype="float32"), trainable=True
        )
        self.bt = tf.Variable(
            initial_value=b_init(shape=(units,), dtype="float32"), trainable=True
        )
        

    def call(self, inputs):
        H = tf.matmul(inputs, self.w) + self.b
        T = tf.sigmoid(tf.matmul(inputs, self.t) + self.bt, name="transform")
        C = tf.sub(1.0, T, name="carry_gate")
        y = tf.add(tf.mul(H, T), tf.mul(inputs, C), "hw-out")
    
        return  y
def rc_cnn(x, name='', filters=16, stride=1, kernel_size=5,dilation_rate=1,padding='same'):

    f = tf.keras.layers.Conv1D(filters=filters,
                               kernel_size=kernel_size, 
                               dilation_rate=dilation_rate,
                               strides=stride,
                               kernel_initializer=tf.keras.initializers.HeUniform(),
                               padding=padding,
                               name=name)#, activity_regularizer=tf.keras.regularizers.l2(l2=1e-5))
    outputs = []
    for l in x:
        outputs.append(f(l))
        
    return outputs


    
def rc_batchnorm(x, name):


    f = tf.keras.layers.BatchNormalization(name=f'bn_{name}')
    
    outputs = []
    for l in x:
        outputs.append(f(l))
        
    return outputs

        

def rc_maxpool(x, pool_size=2):
    f = tf.keras.layers.MaxPooling1D(pool_size=pool_size)
    outputs = []
    for l in x:
        outputs.append(f(l))
        
    return outputs


def rc_gelu(x):
    f = tf.nn.gelu
    outputs = []
    for l in x:
        outputs.append(f(l))
        
    return outputs


def rc_resnet_block(x, name, kernel_size=[3,3],dilation_rate=[1,1], filters=[16,16],add_residual=True): #simple resnet for viruses#
    '''x: input tensor
       name:name for the block
       kernel_size: a list specifying the kernel size of each conv layer
       dilation_rate: a list specifying the dilation rate of each conv layer
       filter:  a list specifying the number of filters of each conv layer
       shared_weights: whether to use reverse conplement parameter sharing.(True)
       add_residual: whether to add residual connections.(True)
    '''

    xx = rc_cnn(x,
                name=f'{name}{1}',
                filters=filters[0],
                kernel_size=kernel_size[0],
                padding='same',
                dilation_rate=dilation_rate[0])
    xx= rc_gelu(xx)
    xx = rc_batchnorm(xx,name=f'{name}{1}')
    # Create layers
    for n, (k, d, f) in enumerate(zip(kernel_size[1:], dilation_rate[1:], filters[1:])):
        xx = rc_cnn(xx,
                                name=f'{name}{n+2}',
                                filters=f,
                                kernel_size=k,
                                padding='same',
                                dilation_rate=d)
        xx = rc_gelu(xx)
        xx = rc_batchnorm(xx,name=f'{name}{n+2}')
    

    #scale up the skip connection output if the filter sizes are different 
    
    if (filters[-1] != filters[0]  or x[-1].shape[-1] != filters[-1]) and add_residual:
        x = rc_cnn(x,
                    name=f'{name}_skip',
                    filters=f,
                    kernel_size=1,
                    padding='same',
                    dilation_rate=1)
        x = rc_gelu(x)
        x = rc_batchnorm(x,name=f'{name}_skip')
        
    # Add Residue
    outputs = []
    add = tf.keras.layers.Add()
    if add_residual:
        for l in zip(x,xx):
            outputs.append( add(l))  
     
        return rc_gelu(outputs)
    else:
        return rc_gelu(xx)


def ConvolutionalTower(inputs, num_res_blocks=5, add_residual=True):
    'Covolutional tower to increase the receptive filed size based on dilated convolutions'

    x = rc_cnn(inputs, filters=128, stride=1, kernel_size=9, dilation_rate=1, padding='same')
    x = rc_gelu(x)
    x = rc_batchnorm(x,name='block1_1')
    x = rc_maxpool(x,pool_size=2)
    x = rc_cnn(x,name='block1_1',filters=128, stride=1, kernel_size=5, dilation_rate = 2,padding='same')
    x = rc_gelu(x)
    x = rc_batchnorm(x, name='block1_2')
    x = rc_maxpool(x,pool_size=2)

    if num_res_blocks:
        for i,n in enumerate(range(num_res_blocks)):
            x = (lambda x,n : rc_resnet_block(x,
                                             name=f'block2_{n}',
                                             kernel_size=[5,5],
                                             dilation_rate=[3+i,3+i], 
                                             filters=[128,128], 
                                             add_residual=add_residual))(x,n)

    return tf.keras.layers.Add()(x)


class PositionalEmbedding(tf.keras.layers.Layer):
    
    def __init__(self, sequence_length, output_dim, **kwargs):
        super(PositionalEmbedding, self).__init__(**kwargs)
        #word_embedding_matrix = self.get_position_encoding(vocab_size, output_dim)   
        position_embedding_matrix = self.get_position_encoding(sequence_length, output_dim)                                          
        #self.word_embedding_layer = Embedding(
        #    input_dim=vocab_size, output_dim=output_dim,
        #    weights=[word_embedding_matrix],
        #    trainable=False
        #)
        self.position_embedding_layer = tf.keras.layers.Embedding(
            input_dim=sequence_length, output_dim=output_dim,
            weights=[position_embedding_matrix],
            trainable=False
        )
             
    def get_position_encoding(self, seq_len, d, n=10000):
        P = np.zeros((seq_len, d))
        for k in range(seq_len):
            for i in np.arange(int(d/2)):
                denominator = np.power(n, 2*i/d)
                P[k, 2*i] = np.sin(k/denominator)
                P[k, 2*i+1] = np.cos(k/denominator)
        return P
 
 
    def call(self, inputs): 
        sequence_length=tf.shape(inputs)[-1] #length of patch encoding blocks
        batch_size = tf.shape(inputs)[0]
        position_indices =[[c for c in range(sequence_length)] for i in range(batch_size)] #tf.range(tf.shape(inputs)[-2])
        position_indices = tf.Variable(position_indices)
        #embedded_words = self.word_embedding_layer(inputs)
        embedded_indices = self.position_embedding_layer(position_indices)
        return embedded_indices  #embedded_words + 
    


class Patches(tf.keras.layers.Layer):
    
    def __init__(self, num_patches, patch_size, name = "split"):
        super(Patches, self).__init__()
        self.num_patches = num_patches
        self.patch_size = patch_size
        self.layer_name = name

    def call(self, data):
        batch_size = tf.shape(data)[0]
        splitted_seq = tf.split(data, num_or_size_splits=self.num_patches, axis=1 ,num=self.patch_size, name=self.layer_name)
        patches = tf.stack( splitted_seq , axis=1, name='stack')
        patches = tf.reshape(patches, [batch_size,self.num_patches ,self.patch_size*4])
       
        ##patch_dims = patches.shape[-1]
        ##patches = tf.reshape(patches, [batch_size, -1, patch_dims])
        
        return patches

    

class PatchEncoder(tf.keras.layers.Layer): #Parch encoding + Position encoding 
    def __init__(self, num_patches, projection_dim=None,embed_input=False,use_sine=True): #num_patches == sequence length when input comes from a conv block
        super(PatchEncoder, self).__init__()
        self.num_patches = num_patches
        
        if embed_input is True:
            self.projection = tf.keras.layers.Dense(units=projection_dim)
        else:
            self.projection = None
            
        if use_sine == False:
            self.position_embedding_layer = tf.keras.layers.Embedding(
                input_dim=num_patches, output_dim=projection_dim
            )
        else:
            position_embedding_matrix = self.get_position_encoding(num_patches, projection_dim)                                          
        
            self.position_embedding_layer = tf.keras.layers.Embedding(
                input_dim=num_patches, output_dim=projection_dim,
                weights=[position_embedding_matrix],
                trainable=False
            )
             
    def get_position_encoding(self, seq_len, d, n=10000):
        P = np.zeros((seq_len, d))
        for k in range(seq_len):
            for i in np.arange(int(d/2)):
                denominator = np.power(n, 2*i/d)
                P[k, 2*i] = np.sin(k/denominator)
                P[k, 2*i+1] = np.cos(k/denominator)
        return P

    def call(self, patches):
        positions = tf.range(start=0, limit=self.num_patches, delta=1)
        if self.projection is not None:
            input_projection=self.projection(patches)
        else:
            input_projection = patches
            
        encoded = input_projection + self.position_embedding_layer(positions)
        
        
        return encoded
    
def mlp(x, hidden_units, dropout_rate):
    for units in hidden_units:
        x = tf.keras.layers.Dense(units, activation=tf.nn.gelu)(x)
        x = tf.keras.layers.Dropout(dropout_rate)(x)
    return x

def Baseline_model(type_spec=None,input_shape=None): #archeae model 1
    f1input = tf.keras.Input(shape=input_shape,type_spec=type_spec,name="forward_1")
    f2input = tf.keras.Input(shape=input_shape,type_spec=type_spec,name="forward_2")
    f3input = tf.keras.Input(shape=input_shape,type_spec=type_spec,name="forward_3")
    r1input = tf.keras.Input(shape=input_shape,type_spec=type_spec,name="reverse_1")
    r2input = tf.keras.Input(shape=input_shape,type_spec=type_spec,name="reverse_2")
    r3input = tf.keras.Input(shape=input_shape,type_spec=type_spec,name="reverse_3")
    embedding_layer = tf.keras.layers.Embedding(22, 4, name="aa", mask_zero=True)
    embeddings = []

    for l in [f1input,f2input,f3input,r1input,r2input,r3input]:
        embeddings.append(embedding_layer(l))
    #A block 
    x=ConvolutionalTower(embeddings, num_res_blocks=None)
    x=tf.keras.layers.GlobalMaxPool1D()(x)
    #C block 
    x = tf.keras.layers.Dropout(0.1)(x)
    x = tf.keras.layers.Dense(128, activation=tf.nn.gelu, name='augdense-1')(x)
    x = tf.keras.layers.Dropout(0.1)(x)
    x = tf.keras.layers.Dense(128, activation=tf.nn.gelu,name='augdense-2')(x)
    out = tf.keras.layers.Dense(4,name='outdense')(x)
    return [f1input,f2input,f3input,r1input,r2input,r3input],out

def Res_model(type_spec=None,input_shape=None): #archeae model 1
    f1input = tf.keras.Input(shape=input_shape,type_spec=type_spec,name="forward_1")
    f2input = tf.keras.Input(shape=input_shape,type_spec=type_spec,name="forward_2")
    f3input = tf.keras.Input(shape=input_shape,type_spec=type_spec,name="forward_3")
    r1input = tf.keras.Input(shape=input_shape,type_spec=type_spec,name="reverse_1")
    r2input = tf.keras.Input(shape=input_shape,type_spec=type_spec,name="reverse_2")
    r3input = tf.keras.Input(shape=input_shape,type_spec=type_spec,name="reverse_3")
    embedding_layer = tf.keras.layers.Embedding(22, 4, name="aa", mask_zero=True)
    embeddings = []

    for l in [f1input,f2input,f3input,r1input,r2input,r3input]:
        embeddings.append(embedding_layer(l))
    #A block 
    x=ConvolutionalTower(embeddings, num_res_blocks=5)
    x=tf.keras.layers.GlobalMaxPool1D()(x)
    #C block
    x = tf.keras.layers.Dropout(0.1)(x)
    x = tf.keras.layers.Dense(128, activation=tf.nn.gelu, name='augdense-1')(x)
    x = tf.keras.layers.Dropout(0.1)(x)
    x = tf.keras.layers.Dense(128, activation=tf.nn.gelu,name='augdense-2')(x)
    out = tf.keras.layers.Dense(4,name='outdense')(x)
    return [f1input,f2input,f3input,r1input,r2input,r3input],out

def WRes_model(type_spec=None,input_shape=None): #archeae model 1
    f1input = tf.keras.Input(shape=input_shape,type_spec=type_spec,name="forward_1")
    f2input = tf.keras.Input(shape=input_shape,type_spec=type_spec,name="forward_2")
    f3input = tf.keras.Input(shape=input_shape,type_spec=type_spec,name="forward_3")
    r1input = tf.keras.Input(shape=input_shape,type_spec=type_spec,name="reverse_1")
    r2input = tf.keras.Input(shape=input_shape,type_spec=type_spec,name="reverse_2")
    r3input = tf.keras.Input(shape=input_shape,type_spec=type_spec,name="reverse_3")
    embedding_layer = tf.keras.layers.Embedding(22, 4, name="aa", mask_zero=True)
    embeddings = []

    for l in [f1input,f2input,f3input,r1input,r2input,r3input]:
        embeddings.append(embedding_layer(l))
    #B block
    x=ConvolutionalTower(embeddings, num_res_blocks=5, add_residual=False)
    x=tf.keras.layers.GlobalMaxPool1D()(x)
    #C block
    x = tf.keras.layers.Dropout(0.1)(x)
    x = tf.keras.layers.Dense(128, activation=tf.nn.gelu, name='augdense-1')(x)
    x = tf.keras.layers.Dropout(0.1)(x)
    x = tf.keras.layers.Dense(128, activation=tf.nn.gelu,name='augdense-2')(x)
    out = tf.keras.layers.Dense(4,name='outdense')(x)
    return [f1input,f2input,f3input,r1input,r2input,r3input],out

def LSTM_model(type_spec=None,input_shape=None): #archeae model 1
    f1input = tf.keras.Input(shape=input_shape,type_spec=type_spec,name="forward_1")
    f2input = tf.keras.Input(shape=input_shape,type_spec=type_spec,name="forward_2")
    f3input = tf.keras.Input(shape=input_shape,type_spec=type_spec,name="forward_3")
    r1input = tf.keras.Input(shape=input_shape,type_spec=type_spec,name="reverse_1")
    r2input = tf.keras.Input(shape=input_shape,type_spec=type_spec,name="reverse_2")
    r3input = tf.keras.Input(shape=input_shape,type_spec=type_spec,name="reverse_3")
    embedding_layer = tf.keras.layers.Embedding(22, 4, name="aa", mask_zero=True)
    embeddings = []
    for l in [f1input,f2input,f3input,r1input,r2input,r3input]:
        embeddings.append(embedding_layer(l))
        
    x=ConvolutionalTower(embeddings,num_res_blocks=5)
    #x=tf.keras.layers.GlobalMaxPool1D()(x)
    x=tf.keras.layers.Bidirectional(tf.keras.layers.LSTM(128, name='lstm'),name='bidirlstm')(x)
    x = tf.keras.layers.Dropout(0.1)(x)
    x = tf.keras.layers.Dense(128, activation=tf.nn.gelu, name='augdense-1')(x)
    x = tf.keras.layers.Dropout(0.1)(x)
    x = tf.keras.layers.Dense(128, activation=tf.nn.gelu,name='augdense-2')(x)
#     x = tf.keras.layers.Dropout(0.1)(x)
#     x = tf.keras.layers.Dense(128, activation=tf.nn.gelu,name='augdense-3')(x)
    out = tf.keras.layers.Dense(4,name='outdense')(x)
    return [f1input,f2input,f3input,r1input,r2input,r3input],out

def Vitra(input_shape=(None,),type_spec=None,num_patches=512,transformer_layers = 4,num_heads=4,  att_dropout=0.1,
                          projection_dim=128, att_hidden_units=[128,128],mlp_hidden_units=[128,128],
                          mlp_dropout=0.1, use_global=True, global_type='max'):
    
    f1input = tf.keras.Input(shape=input_shape,type_spec=type_spec,name="forward_1")
    f2input = tf.keras.Input(shape=input_shape,type_spec=type_spec,name="forward_2")
    f3input = tf.keras.Input(shape=input_shape,type_spec=type_spec,name="forward_3")
    r1input = tf.keras.Input(shape=input_shape,type_spec=type_spec,name="reverse_1")
    r2input = tf.keras.Input(shape=input_shape,type_spec=type_spec,name="reverse_2")
    r3input = tf.keras.Input(shape=input_shape,type_spec=type_spec,name="reverse_3")
    embedding_layer = tf.keras.layers.Embedding(22, 4, name="aa", mask_zero=True)
    embeddings = []
    for l in [f1input,f2input,f3input,r1input,r2input,r3input]:
        embeddings.append(embedding_layer(l))
    # Create patches.
    patches=ConvolutionalTower(embeddings, num_res_blocks=5)
    #patches = Patches(num_patches=num_patches,patch_size=patch_size)(inputs)
    # Encode patches.
    encoded_patches = PatchEncoder(num_patches=num_patches, projection_dim=projection_dim)(patches)

    # Create multiple layers of the Transformer block.
    for _ in range(transformer_layers):
        # Layer normalization 1.
        x1 = tf.keras.layers.LayerNormalization(epsilon=1e-6)(encoded_patches)
        # Create a multi-head attention layer.
        attention_output = tf.keras.layers.MultiHeadAttention(
            num_heads=num_heads, key_dim=projection_dim, dropout=att_dropout
        )(x1, x1)
        # Skip connection 1.
        x2 = tf.keras.layers.Add()([attention_output, encoded_patches])
        # Layer normalization 2.
        x3 = tf.keras.layers.LayerNormalization(epsilon=1e-6)(x2)
        # MLP.
        x3 = mlp(x3, hidden_units=att_hidden_units, dropout_rate=mlp_dropout)
        # Skip connection 2.
        encoded_patches = tf.keras.layers.Add()([x3, x2])

    # Create a [batch_size, projection_dim] tensor.
    representation = tf.keras.layers.LayerNormalization(epsilon=1e-6)(encoded_patches)
    
    if use_global == True:
        if global_type == 'average':
            representation=tf.keras.layers.GlobalAveragePooling1D()(representation)
        elif global_type == 'max':
            representation = tf.keras.layers.GlobalMaxPooling1D()(representation)
    else:
        representation = tf.keras.layers.Flatten()(representation)
        
    representation = tf.keras.layers.Dropout(0.1)(representation)
    # Add MLP.
    features = mlp(representation, hidden_units=mlp_hidden_units, dropout_rate=0.5)
    # Classify outputs.
    logits = tf.keras.layers.Dense(4)(features)
    # Create the Keras model.
    return [f1input,f2input,f3input,r1input,r2input,r3input],logits

