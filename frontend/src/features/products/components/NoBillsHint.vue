<template>
  <p
    class="alert"
    data-testid="no-bills-hint"
  >
    库里还没有该税号的提单。两条路：到
    <RouterLink to="/">
      首页底部的「导入提单 CSV」
    </RouterLink>
    导入授权数据；或没有提单时直接点上方「AI 买家发现」，让 AI 从品名捞市场客户。
  </p>
</template>
