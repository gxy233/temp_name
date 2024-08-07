import os
import sys
if os.path.join(os.path.dirname(__file__),r'../..') not in sys.path:
    sys.path.append(os.path.join(os.path.dirname(__file__),r'../..'))

import math
import argparse

import torch
import torch.optim as optim
import torch.optim.lr_scheduler as lr_scheduler
from torch.utils.tensorboard import SummaryWriter
from torchvision import transforms
import torchvision
import torch.nn.functional as F

from util.utils import  train_one_epoch_front,train_one_epoch_back,train_one_epoch_mid, evaluate_front, evaluate_mid, evaluate_back
from dataloader.load_data import get_dataloader
from util.get_optimizer import get_optimizer
from util.create_model import create_model

#### 第一个模块
def train_front(args, comargs, cache, evacache):
    device = torch.device(args.device if torch.cuda.is_available() else "cpu")

    os.makedirs(f"./weights/{comargs.exp_name}/{args.partname}",exist_ok=True)
   

    train_loader,val_loader = get_dataloader(comargs.dataset,batch_size=comargs.batch_size)
    
    
#### 初始化front模型
    model = create_model(model_name=comargs.model_name, part='front', img_size=comargs.img_size, patch_size=comargs.patch_size, aux_depth_list=args.aux_depth_list,
                         num_classes=args.num_classes,device=args.device)



    if args.weights != "":
        assert os.path.exists(args.weights), "weights file: '{}' not exist.".format(args.weights)
        weights_dict = torch.load(args.weights, map_location=args.device)


        # 删除不需要的权重
        del_keys = ['head.weight', 'head.bias'] if model.has_logits \
            else ['pre_logits.fc.weight', 'pre_logits.fc.bias', 'head.weight', 'head.bias']
        for k in del_keys:
            if k in weights_dict:
                del weights_dict[k]
        
        # 加载模型时忽略不匹配的权重 
        missing_keys, unexpected_keys = model.load_state_dict(weights_dict, strict=False)
        print("Missing keys:", missing_keys)
        print("Unexpected keys:", unexpected_keys)

    if args.freeze_layers:
        for name, para in model.named_parameters():
            # 除head, pre_logits外，其他权重全部冻结
            if "head" not in name and "pre_logits" not in name:
                para.requires_grad_(False)
            else:
                print("training {}".format(name))

    pg = [p for p in model.parameters() if p.requires_grad]
    optimizer = get_optimizer(pg,comargs.optimizer,comargs.lr,comargs.momentum,comargs.weight_decay)
    
    # # Scheduler https://arxiv.org/pdf/1812.01187.pdf
    # # lf = lambda x: ((1 + math.cos(x * math.pi / args.epochs)) / 2) * (1 - args.lrf) + args.lrf  # cosine
    
    milestones = comargs.milestones  # 在第 80 和 120 个 epoch 时衰减学习率
    lr_decay_rate = comargs.lr_decay_rate
    
# 创建学习率调度器
    scheduler = lr_scheduler.MultiStepLR(optimizer, milestones=milestones, gamma=lr_decay_rate)
    # scheduler = lr_scheduler.LambdaLR(optimizer, lr_lambda=lf)

    for epoch in range(comargs.epochs):
        # train
        pred = train_one_epoch_front(model=model,
                                    optimizer=optimizer,
                                    data_loader=train_loader,
                                    device=device,
                                    cache=cache)

        scheduler.step()

          # validate
        pred = evaluate_front(model=model,
                            data_loader=val_loader,
                            device=device,
                            evacache=evacache
                            )

        torch.save(model.state_dict(), f"./weights/{comargs.exp_name}/{args.partname}/model-{epoch}.pth")




#### 中间模块
def train_mid(args, comargs, in_cache, out_cache, in_evacache, out_evacache):
    device = torch.device(args.device if torch.cuda.is_available() else "cpu")

    os.makedirs(f"./weights/{comargs.exp_name}/{args.partname}",exist_ok=True)


    
#### 初始化mid模型
    model = create_model(model_name=comargs.model_name, part='mid', img_size=comargs.img_size, patch_size=comargs.patch_size, aux_depth_list=args.aux_depth_list,
                         num_classes=args.num_classes,device=args.device)



    if args.weights != "":
        assert os.path.exists(args.weights), "weights file: '{}' not exist.".format(args.weights)
        weights_dict = torch.load(args.weights, map_location=device)


        # 删除不需要的权重
        del_keys = ['head.weight', 'head.bias'] if model.has_logits \
            else ['pre_logits.fc.weight', 'pre_logits.fc.bias', 'head.weight', 'head.bias']
        for k in del_keys:
            if k in weights_dict:
                del weights_dict[k]
        
        # 加载模型时忽略不匹配的权重 
        missing_keys, unexpected_keys = model.load_state_dict(weights_dict, strict=False)
        print("Missing keys:", missing_keys)
        print("Unexpected keys:", unexpected_keys)

    if args.freeze_layers:
        for name, para in model.named_parameters():
            # 除head, pre_logits外，其他权重全部冻结
            if "head" not in name and "pre_logits" not in name:
                para.requires_grad_(False)
            else:
                print("training {}".format(name))

    pg = [p for p in model.parameters() if p.requires_grad]
    optimizer = get_optimizer(pg,comargs.optimizer,comargs.lr,comargs.momentum,comargs.weight_decay)

    milestones = comargs.milestones  # 在第 80 和 120 个 epoch 时衰减学习率
    lr_decay_rate = comargs.lr_decay_rate
    
# 创建学习率调度器
    scheduler = lr_scheduler.MultiStepLR(optimizer, milestones=milestones, gamma=lr_decay_rate)
    # scheduler = lr_scheduler.LambdaLR(optimizer, lr_lambda=lf)

    for epoch in range(comargs.epochs):
        # train
        pred = train_one_epoch_mid(model=model,
                                    optimizer=optimizer,
                                    device=device,
                                    in_cache=in_cache,
                                    out_cache=out_cache)

        scheduler.step()

          # validate
        pred = evaluate_mid(model=model,
                            device=device,
                            in_evacache=in_evacache,
                            out_evacache=out_evacache)

        torch.save(model.state_dict(), f"./weights/{comargs.exp_name}/{args.partname}/model-{epoch}.pth")






#### 最后一个模块
def train_back(args, comargs, cache, evacache):
    device = torch.device(args.device if torch.cuda.is_available() else "cpu")

    
    os.makedirs(f"./weights/{comargs.exp_name}/{args.partname}",exist_ok=True)

    log_dir=f'./runs/{comargs.exp_name}'
    os.makedirs(log_dir,exist_ok=True)
    
    tb_writer = SummaryWriter(log_dir=log_dir)



#### 初始化back模型
    model = create_model(model_name=comargs.model_name, part='back', img_size=comargs.img_size, patch_size=comargs.patch_size, aux_depth_list=args.aux_depth_list,
                         num_classes=args.num_classes, device=args.device)


    if args.weights != "":
        assert os.path.exists(args.weights), "weights file: '{}' not exist.".format(args.weights)
        weights_dict = torch.load(args.weights, map_location=args.device)


        # 删除不需要的权重
        del_keys = ['head.weight', 'head.bias'] if model.has_logits \
            else ['pre_logits.fc.weight', 'pre_logits.fc.bias', 'head.weight', 'head.bias']
        for k in del_keys:
            if k in weights_dict:
                del weights_dict[k]
        
        # 加载模型时忽略不匹配的权重 
        missing_keys, unexpected_keys = model.load_state_dict(weights_dict, strict=False)
        print("Missing keys:", missing_keys)
        print("Unexpected keys:", unexpected_keys)

    if args.freeze_layers:
        for name, para in model.named_parameters():
            # 除head, pre_logits外，其他权重全部冻结
            if "head" not in name and "pre_logits" not in name:
                para.requires_grad_(False)
            else:
                print("training {}".format(name))

    pg = [p for p in model.parameters() if p.requires_grad]

    
    optimizer = get_optimizer(pg,comargs.optimizer,comargs.lr,comargs.momentum,comargs.weight_decay)
    
    # # Scheduler https://arxiv.org/pdf/1812.01187.pdf
    # # lf = lambda x: ((1 + math.cos(x * math.pi / args.epochs)) / 2) * (1 - args.lrf) + args.lrf  # cosine
    
    milestones = comargs.milestones  # 在第 80 和 120 个 epoch 时衰减学习率
    lr_decay_rate = comargs.lr_decay_rate

# 创建学习率调度器
    scheduler = lr_scheduler.MultiStepLR(optimizer, milestones=milestones, gamma=lr_decay_rate)
    # scheduler = lr_scheduler.LambdaLR(optimizer, lr_lambda=lf)

    for epoch in range(comargs.epochs):
        
        print(f'cache len: {len(cache)}')
        
        # train
        train_loss, train_acc = train_one_epoch_back(model=model,
                                                optimizer=optimizer,
                                                device=device,
                                                epoch=epoch,
                                                cache=cache
                                                )

        scheduler.step()

        # validate
        val_loss, val_acc = evaluate_back(model=model,
                                     device=device,
                                     epoch=epoch,
                                     evacache=evacache)

        tags = ["train_loss", "train_acc", "val_loss", "val_acc", "learning_rate"]
        tb_writer.add_scalar(tags[0], train_loss, epoch)
        tb_writer.add_scalar(tags[1], train_acc, epoch)
        tb_writer.add_scalar(tags[2], val_loss, epoch)
        tb_writer.add_scalar(tags[3], val_acc, epoch)
        tb_writer.add_scalar(tags[4], optimizer.param_groups[0]["lr"], epoch)

        torch.save(model.state_dict(), f"./weights/{comargs.exp_name}/{args.partname}/model-{epoch}.pth")


