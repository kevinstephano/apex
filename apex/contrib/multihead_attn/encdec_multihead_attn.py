import torch
from torch import nn
from torch.nn import Parameter
import torch.nn.functional as F
from torch.autograd.variable  import Variable

from .encdec_multihead_attn_func               import encdec_attn_func
from .fast_encdec_multihead_attn_func          import fast_encdec_attn_func
from .fast_encdec_multihead_attn_norm_add_func import fast_encdec_attn_norm_add_func

class EncdecMultiheadAttn(nn.Module):
    """Multi-headed attention.

    See "Attention Is All You Need" for more details.
    """
    def __init__(self, embed_dim, num_heads, dropout=0., bias=False, include_norm_add=False, impl='fast'):
        super().__init__()
        self.embed_dim = embed_dim
        self.num_heads = num_heads
        self.dropout = dropout
        self.head_dim = embed_dim // num_heads
        assert self.head_dim * num_heads == self.embed_dim, "embed_dim must be divisible by num_heads"
        self.bias = bias
        self.include_norm_add = include_norm_add
        self.impl = impl
        self.scaling = self.head_dim**-0.5

        self.in_proj_weight_q    = Parameter(torch.Tensor(embed_dim, embed_dim))
        self.in_proj_weight_kv   = Parameter(torch.Tensor(2*embed_dim, embed_dim))
        self.out_proj_weight     = Parameter(torch.Tensor(embed_dim, embed_dim))
        if self.bias:
            self.in_proj_bias_q  = Parameter(torch.Tensor(embed_dim))
            self.in_proj_bias_kv = Parameter(torch.Tensor(2*embed_dim))
        else:
            self.register_parameter('in_proj_bias', None)
        if self.include_norm_add :
            self.lyr_nrm_gamma_weights = Parameter(torch.Tensor(embed_dim))
            self.lyr_nrm_beta_weights  = Parameter(torch.Tensor(embed_dim))
        self.reset_parameters()
        
        if self.include_norm_add :
            if   impl == 'fast'    : self.attn_func = fast_encdec_attn_norm_add_func
            elif impl == 'default' : assert False, "TODO: make default self attn with norm and add."
            else :                   assert False, "Unsupported impl: {} !".format(impl)
        else :
            if   impl == 'fast'    : self.attn_func = fast_encdec_attn_func
            elif impl == 'default' : self.attn_func = encdec_attn_func
            else :                   assert False, "Unsupported impl: {} !".format(impl)

    def reset_parameters(self):
        nn.init.xavier_uniform_(self.in_proj_weight_q)
        nn.init.xavier_uniform_(self.in_proj_weight_kv)
        nn.init.xavier_uniform_(self.out_proj_weight)
        if self.bias:
            nn.init.constant_(self.in_proj_bias_q, 0.)
            nn.init.constant_(self.in_proj_bias_kv, 0.)
            nn.init.constant_(self.out_proj.bias, 0.)
        if self.include_norm_add :
            nn.init.ones_(self.lyr_nrm_gamma_weights)
            nn.init.zeros_(self.lyr_nrm_beta_weights)

    def forward(self, query, key, value, key_padding_mask=None, need_weights=False, attn_mask=None, is_training=True) :
        """Input shape: Time x Batch x Channel

        Self-attention can be implemented by passing in the same arguments for
        query, key and value. Future timesteps can be masked with the
        `mask_future_timesteps` argument. Padding elements can be excluded from
        the key by passing a binary ByteTensor (`key_padding_mask`) with shape:
        batch x src_len, where padding elements are indicated by 1s.
        """

        if key_padding_mask is not None :
            assert (attn_mask is None), "ERROR attn_mask and key_padding_mask should not be both defined!"
            mask = key_padding_mask
        elif attn_mask is not None :
            mask = attn_mask
        else :
            mask = None

        if self.include_norm_add :
            outputs = self.attn_func(attn_mask is not None, is_training, self.num_heads, query, key, 
                                     self.lyr_nrm_gamma_weights, self.lyr_nrm_beta_weights, 
                                     self.in_proj_weight_q, self.in_proj_weight_kv, self.out_proj_weight, mask, self.dropout)
        else :
            if self.impl == 'default' :
                outputs = self.attn_func(attn_mask is not None, is_training, self.num_heads, self.scaling, query, key, 
                                         self.in_proj_weight_q, self.in_proj_weight_kv, 
                                         self.out_proj_weight, mask, self.dropout)
            else :
                outputs = self.attn_func(attn_mask is not None, is_training, self.num_heads, query, key, 
                                         self.in_proj_weight_q, self.in_proj_weight_kv, 
                                         self.out_proj_weight, mask, self.dropout)

        return outputs,None
