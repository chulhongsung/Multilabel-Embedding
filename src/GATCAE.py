#%%
import os
import pandas as pd
import numpy as np

from skmultilearn.dataset import load_dataset

import tensorflow as tf
import tensorflow.keras as K
from tensorflow.keras import preprocessing
#%%
class Feature_Encoder(K.layers.Layer):
    def __init__(self, dim_model):
        super(Feature_Encoder, self).__init__()
        self.n_layer = len(dim_model)
        self.dim_model = dim_model
        self.encoder = [K.layers.Dense(self.dim_model[i],
                                       activation=tf.keras.layers.LeakyReLU(alpha=0.3)) for i in range(self.n_layer)]
        
    def get_config(self):
        config = super().get_config().copy()
        config.update({
            'encoder': self.encoder
        })
        return config
        
    def call(self, x):
        for i in range(self.n_layer):
            x = self.encoder[i](x)
        return x
#%%
class GAT(K.layers.Layer):
    def __init__(self, num_labels, dim_embedding1, dim_embedding2, dropout):
        super(GAT, self).__init__()
        self.embedding_layer = tf.keras.layers.Embedding(num_labels+1, dim_embedding1, mask_zero=True)
        self.wq = K.layers.Dense(dim_embedding2)
        self.wk = K.layers.Dense(dim_embedding2)
        self.wv = K.layers.Dense(dim_embedding2)
        self.dropout1 = K.layers.Dropout(dropout)   
        self.dropout2 = K.layers.Dropout(dropout)
        self.dropout3 = K.layers.Dropout(dropout)
        self.dim_embedding2 = dim_embedding2
        
    def attention(self, q, k, v, label):
        matmul_qk = tf.linalg.matmul(q, k, transpose_b=True)
    
        dk = tf.cast(tf.shape(k)[-1], tf.float32)
    
        scaled_attention_logits = matmul_qk / tf.math.sqrt(dk)
    
        attention_weights  = tf.transpose(tf.cast(tf.where(label == 0, 0, 1)[:,tf.newaxis,:], tf.float32), [0, 2, 1]) * tf.nn.softmax(scaled_attention_logits, axis=-1)
        
        output = tf.matmul(attention_weights, v)
        
        return output, attention_weights
    
    def get_config(self):
        config = super().get_config().copy()
        config.update({
            'embedding': self.embedding_layer,
            'query': self.wq,
            'key': self.wk,
            'value': self.wv
        })
        
        return config
    
    def call(self, input):
        x = self.embedding_layer(input)
        q = self.dropout1(self.wq(x))
        k = self.dropout2(self.wk(x))
        v = self.dropout3(self.wv(x))
        self_attention, _ = self.attention(q, k, v, input)
        
        return self_attention 
#%% 
class LabelSet_Attention(K.layers.Layer):
    def __init__(self, dim_embedding):
        super(LabelSet_Attention, self).__init__()
        self.w = K.layers.Dense(dim_embedding)
        self.dim_embedding = dim_embedding
        
    def get_config(self):
        config = super().get_config().copy()
        config.update({
            'w': self.w,
        })
        
        return config
        
    def call(self, input, label):
        q = self.w(input)
        k = self.w(input)
        matmul_qk = tf.linalg.matmul(q, k, transpose_b=True)
        dk = tf.cast(tf.shape(k)[-1], tf.float32)
        scaled_attention_logits = matmul_qk / tf.math.sqrt(dk)        
        weight = tf.where(label != 0, tf.exp(tf.reduce_sum(scaled_attention_logits, -1)), 0) / tf.reduce_sum(tf.where(label != 0, tf.exp(tf.reduce_sum(scaled_attention_logits, -1)), 0), -1)[:, tf.newaxis]
        label_set = tf.linalg.matmul(weight[:, tf.newaxis, :], input)
        
        return label_set 
#%%
class Label_Encoder(K.layers.Layer):
    def __init__(self, dim_model):
        super(Label_Encoder, self).__init__()
        self.n_layer = len(dim_model)
        self.dim_model = dim_model
        self.encoder = [K.layers.Dense(self.dim_model[i],
                                       activation=tf.keras.layers.LeakyReLU(alpha=0.3)) for i in range(self.n_layer)]
        
    def get_config(self):
        config = super().get_config().copy()
        config.update({
            'encoder': self.encoder
        })
        return config
        
    def call(self, x):
        for i in range(self.n_layer):
            x = self.encoder[i](x)
        return x
#%%
class Label_Decoder(K.layers.Layer):
    def __init__(self, dim_model):
        super(Label_Decoder, self).__init__()
        self.n_layer = len(dim_model)
        self.dim_model = dim_model
        self.decoder = [K.layers.Dense(self.dim_model[i],
                                       activation=tf.keras.layers.LeakyReLU(alpha=0.3)) for i in range(self.n_layer-1)]
        self.decoder.append(K.layers.Dense(self.dim_model[self.n_layer-1], activation='sigmoid'))
        
    def get_config(self):
        config = super().get_config().copy()
        config.update({
            'decoder': self.decoder
        })
        return config
        
    def call(self, x):
        for i in range(self.n_layer):
            x = self.decoder[i](x)
        return x
#%%
class GATCAE(K.models.Model):
    def __init__(self, num_labels, dim_embedding1, dim_embedding2, dim_embedding3, label_encoder_dim, label_decoder_dim, feature_encoder_dim, dropout=0.05):
        super(GATCAE, self).__init__()
        self.graph_attention_network = GAT(num_labels, dim_embedding1, dim_embedding2, dropout)
        self.label_representation = LabelSet_Attention(dim_embedding3)
        self.label_encoder = Label_Encoder(label_encoder_dim)
        self.label_decoder = Label_Decoder(label_decoder_dim)
        self.feature_encoder = Feature_Encoder(feature_encoder_dim)
        
    def get_config(self):
        config = super().get_config().copy()
        config.update({
            'graph_attention_network': self.graph_attention_network,
            'label_representation': self.label_representation,
            'label_encoder': self.label_encoder,
            'label_decoder': self.label_decoder,
            'feature_encoder': self.feature_encoder
        })
        return config
    
    def call(self, input):
        feature, label = input
        node_feature = self.graph_attention_network(label)
        label_list_feature = self.label_representation(node_feature, label)
        latent_label_feature = self.label_encoder(label_list_feature)
        recon_label = self.label_decoder(latent_label_feature)
        latent_feature = self.feature_encoder(feature)
        
        return latent_feature, latent_label_feature, recon_label
#%%
class CCA_Loss(K.losses.Loss):
    def __init__(self, regularization_factor=0.1):
        super().__init__()
        self.regularization_factor = regularization_factor

    def call(self, emb_feature, emb_label):
        emb_label = tf.squeeze(emb_label)
        num_instance = emb_feature.shape[0]
        c1 = emb_feature - emb_label
        c2 = tf.linalg.matmul(emb_feature, emb_feature, transpose_b=True) - tf.eye(num_instance)
        c3 = tf.linalg.matmul(emb_label, emb_label, transpose_b=True) - tf.eye(num_instance)
        loss = tf.linalg.trace(tf.matmul(c1, c1, transpose_a=True)) + self.regularization_factor * tf.linalg.trace(tf.matmul(c2, c2, transpose_a=True) +
                                                                                      tf.matmul(c3, c3, transpose_a=True))
        return loss
#%%
X, y, feature_names, label_names = load_dataset('tmc2007_500', 'train')
#%%
# label = y.todense()
# rows, cols = np.where(label != 0)
# label_lst = list(zip(rows, cols))
# values = set(rows.tolist())
# next(iter(label_lst))
# label_list = [[y[1]+1 for y in label_lst if y[0]==x] for x in values]

# MAX_PAD_LENGTH =  max(map(lambda x: len(x), label_list))
# padded_label = preprocessing.sequence.pad_sequences(label_list,
#                                 maxlen=MAX_PAD_LENGTH,
#                                 padding='post')
# np.save('tmc2007_label.npy',padded_label)
label_idx = np.load('tmc2007_label.npy')
#%%
gatcae = GATCAE2(22, 100, 100, 10, [10], [22], [10])
cl = CCA_Loss()
optimizer = K.optimizers.Adam(learning_rate=0.001)
train_loss = tf.keras.metrics.Mean(name='train_loss')
#%%
BATCH_SIZE = 500

tmc2007 = tf.data.Dataset.from_tensor_slices((np.array(X.todense(), dtype=np.float32), label_idx, np.array(y.todense(), dtype=np.float32)))
tmc_data = tmc2007
tmc_data_batch = tmc_data.batch(BATCH_SIZE)
#%%
@tf.function
def train_step(model, feature, label_idx, label):
    with tf.GradientTape() as tape:
        a, b, c = model([feature, label_idx])
        accuracy_loss = tf.math.reduce_sum(tf.map_fn(fn=lambda t: tf.math.divide(tf.math.reduce_sum(tf.exp(tf.reshape(t[0][(t[0] * t[1]) == 0], (tf.math.reduce_sum(tf.cast((t[0] * t[1]) == 0, tf.int32)), 1)) - tf.reshape(t[0][(t[0] * t[1]) != 0], (1, tf.math.reduce_sum(tf.cast((t[0] * t[1]) != 0, tf.int32))) ) )), tf.math.reduce_sum(tf.cast(t[1] == 0, tf.float32)) * tf.math.reduce_sum(tf.cast(t[1] != 0, tf.float32))),
                                                     elems= (tf.squeeze(c), label),
                                                     fn_output_signature=tf.float32))
        cca_loss = cl(a, b)
        loss =  cca_loss + 1 * accuracy_loss 
    grad = tape.gradient(loss, model.weights)
    optimizer.apply_gradients(zip(grad, model.weights))
    train_loss(loss)
#%%
EPOCHS = 400

for epoch in range(EPOCHS):
    for batch_feature, batch_label_idx, batch_label in iter(tmc_data_batch):
        train_step(gatcae, batch_feature, batch_label_idx, batch_label)
    template = 'EPOCH: {}, Train Loss: {}'
    print(template.format(epoch+1, train_loss.result()))