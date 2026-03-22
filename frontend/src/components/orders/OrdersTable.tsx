import { useQuery } from "@tanstack/react-query";
import { fetchOrders, type Order } from "../../api/orders";

export function OrdersTable() {
  const { data: orders = [], isLoading } = useQuery({
    queryKey: ["orders"],
    queryFn: () => fetchOrders(50),
    refetchInterval: 3000,
  });

  if (isLoading) {
    return <div className="bg-surface-2 rounded-xl p-5 animate-pulse h-48" />;
  }

  return (
    <div className="bg-surface-2 rounded-xl p-5">
      <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-4">
        Recent Orders
      </h2>

      {orders.length === 0 ? (
        <p className="text-gray-500 text-sm text-center py-8">
          No orders yet — strategies are warming up
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-500 text-left border-b border-white/5">
                <th className="pb-2 pr-4">Time</th>
                <th className="pb-2 pr-4">Symbol</th>
                <th className="pb-2 pr-4">Side</th>
                <th className="pb-2 pr-4">Price</th>
                <th className="pb-2 pr-4">Size</th>
                <th className="pb-2 pr-4">Strategy</th>
                <th className="pb-2">Mode</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {orders.map((order) => (
                <OrderRow key={order.id} order={order} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function OrderRow({ order }: { order: Order }) {
  const isBuy = order.side === "BUY";
  const time = new Date(order.created_at).toLocaleTimeString();

  return (
    <tr className="hover:bg-white/5 transition-colors" title={order.reason}>
      <td className="py-2 pr-4 text-gray-500 text-xs">{time}</td>
      <td className="py-2 pr-4 font-medium">{order.symbol}</td>
      <td className="py-2 pr-4">
        <span
          className={`text-xs font-bold px-2 py-0.5 rounded ${
            isBuy
              ? "bg-bull/20 text-bull"
              : "bg-bear/20 text-bear"
          }`}
        >
          {order.side}
        </span>
      </td>
      <td className="py-2 pr-4 text-gray-300">
        ${order.price.toLocaleString()}
      </td>
      <td className="py-2 pr-4 text-gray-300">${order.size_usd.toFixed(2)}</td>
      <td className="py-2 pr-4 text-gray-400 text-xs">{order.strategy || "—"}</td>
      <td className="py-2">
        <span
          className={`text-xs px-1.5 py-0.5 rounded ${
            order.mode === "PAPER"
              ? "bg-blue-500/20 text-blue-400"
              : "bg-yellow-500/20 text-yellow-400"
          }`}
        >
          {order.mode}
        </span>
      </td>
    </tr>
  );
}
