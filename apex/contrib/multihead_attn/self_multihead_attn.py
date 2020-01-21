# Copyright (c) 2017-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the license found in the LICENSE file in
# the root directory of this source tree. An additional grant of patent rights
# can be found in the PATENTS file in the same directory.

import torch
from torch import nn
from torch.nn import Parameter
import torch.nn.functional as F
from torch.autograd.variable  import Variable

import fast_self_multihead_attn

class SelfAttnFunc(torch.autograd.Function) :
    @staticmethod
    def forward(ctx, use_time_mask, is_training, heads, inputs, input_weights, output_weights, pad_mask, dropout_prob) :
        heads_t        = Variable(torch.tensor([heads]))
        dropout_prob_t = Variable(torch.tensor([dropout_prob]))
        null_tensor    = torch.tensor([])
        use_mask       = (pad_mask is not None)

        input_lin_results,                                              \
        softmax_results,                                                \
        dropout_results,                                                \
        dropout_mask,                                                   \
        matmul2_results,                                                \
        outputs =                                                       \
            fast_self_multihead_attn.forward(                           \
                              use_mask,                                 \
                              use_time_mask,                            \
                              is_training,                              \
                              heads,                                    \
                              inputs,                                   \
                              input_weights,                            \
                              output_weights,                           \
                              pad_mask if use_mask else null_tensor,    \
                              dropout_prob)

        ctx.save_for_backward(heads_t,                                  \
                              matmul2_results,                          \
                              dropout_results,                          \
                              softmax_results,                          \
                              input_lin_results,                        \
                              inputs,                                   \
                              input_weights,                            \
                              output_weights,                           \
                              dropout_mask,                             \
                              dropout_prob_t)

        return outputs.detach()

    @staticmethod
    def backward(ctx, output_grads) :
        heads_t,                                                        \
        matmul2_results,                                                \
        dropout_results,                                                \
        softmax_results,                                                \
        input_lin_results,                                              \
        inputs,                                                         \
        input_weights,                                                  \
        output_weights,                                                 \
        dropout_mask,                                                   \
        dropout_prob_t      = ctx.saved_tensors

        input_grads,                                                    \
        input_weight_grads,                                             \
        output_weight_grads =                                           \
            fast_self_multihead_attn.backward(                          \
                              heads_t[0],                               \
                              output_grads,                             \
                              matmul2_results,                          \
                              dropout_results,                          \
                              softmax_results,                          \
                              input_lin_results,                        \
                              inputs,                                   \
                              input_weights,                            \
                              output_weights,                           \
                              dropout_mask,                             \
                              dropout_prob_t[0])

        return None, None, None, input_grads, input_weight_grads, output_weight_grads, None, None

self_attn_func = SelfAttnFunc.apply

class SelfMultiheadAttn(nn.Module):
    """Multi-headed attention.

    See "Attention Is All You Need" for more details.
    """
    def __init__(self, embed_dim, num_heads, dropout=0., softmax_type='default', bias=False):
        super().__init__()
        self.embed_dim = embed_dim
        self.num_heads = num_heads
        self.dropout = dropout
        self.softmax_type = softmax_type
        self.head_dim = embed_dim // num_heads
        self.bias = bias
        assert self.head_dim * num_heads == self.embed_dim, "embed_dim must be divisible by num_heads"
        self.scaling = self.head_dim**-0.5
        self._mask = None
        self.in_proj_weight  = Parameter(torch.Tensor(3*embed_dim, embed_dim))
        self.out_proj_weight = Parameter(torch.Tensor(embed_dim, embed_dim))
        if self.bias:
            self.in_proj_bias = Parameter(torch.Tensor(3*embed_dim))
        else:
            self.register_parameter('in_proj_bias', None)
        self.reset_parameters()

        self.attn_func = self_attn_func

    def reset_parameters(self):
        nn.init.xavier_uniform_(self.in_proj_weight)
        nn.init.xavier_uniform_(self.out_proj_weight)
        if self.bias:
            nn.init.constant_(self.in_proj_bias, 0.)
            nn.init.constant_(self.out_proj.bias, 0.)

    def forward(self, query, key, value, is_training=True, mask_future_timesteps=False,
                key_padding_mask=None, incremental_state=None,
                need_weights=True, static_kv=False):
        """Input shape: Time x Batch x Channel

        Self-attention can be implemented by passing in the same arguments for
        query, key and value. Future timesteps can be masked with the
        `mask_future_timesteps` argument. Padding elements can be excluded from
        the key by passing a binary ByteTensor (`key_padding_mask`) with shape:
        batch x src_len, where padding elements are indicated by 1s.
        """

        if incremental_state is not None :
            outputs = self.attn_func(mask_future_timesteps, is_training, self.num_heads, query, self.in_proj_weight, self.out_proj_weight, None, self.dropout)
        else :
            outputs = self.attn_func(mask_future_timesteps, is_training, self.num_heads, query, self.in_proj_weight, self.out_proj_weight, key_padding_mask, self.dropout)

        return outputs,None
